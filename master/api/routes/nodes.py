"""
Node registry routes — register, heartbeat, list, and configure distributed worker nodes.

Node configuration is pushed via Redis so the node can hot-reload without restart.
Config channel: config:{node_id}
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..models import NodeConfigUpdate, NodeInfo, NodeRegisterRequest
from ..websocket_manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nodes", tags=["nodes"])

# In-memory node registry (keyed by node_id)
_nodes: dict[str, NodeInfo] = {}

NODE_TIMEOUT_SECONDS = 30


# -----------------------------------------------------------------------
# List / inspect
# -----------------------------------------------------------------------

@router.get("/", response_model=list[NodeInfo])
async def list_nodes():
    _evict_stale()
    return list(_nodes.values())


@router.get("/{node_id}", response_model=NodeInfo)
async def get_node(node_id: str):
    node = _nodes.get(node_id)
    if not node:
        raise HTTPException(404, f"Node '{node_id}' not found")
    return node


# -----------------------------------------------------------------------
# Registration & heartbeat
# -----------------------------------------------------------------------

@router.post("/register", response_model=NodeInfo, status_code=201)
async def register_node(body: NodeRegisterRequest):
    existing = _nodes.get(body.node_id)
    info = NodeInfo(
        node_id=body.node_id,
        host=body.host,
        port=body.port,
        status="active",
        agent_ids=body.agent_ids,
        # preserve any existing agent_configs if node re-registers
        agent_configs=existing.agent_configs if existing else [],
        capabilities=body.capabilities,
        last_seen=datetime.utcnow(),
        tasks_completed=existing.tasks_completed if existing else 0,
        tasks_running=existing.tasks_running if existing else 0,
    )
    _nodes[body.node_id] = info
    await ws_manager.broadcast_notification({
        "type": "node_connected",
        "message": f"Node '{body.node_id}' connected",
        "data": info.model_dump(mode="json"),
    })
    return info


@router.post("/{node_id}/heartbeat", response_model=NodeInfo)
async def heartbeat(node_id: str, agent_ids: Optional[list[str]] = None):
    if node_id not in _nodes:
        raise HTTPException(404, f"Node '{node_id}' not registered")
    _nodes[node_id].last_seen = datetime.utcnow()
    _nodes[node_id].status = "active"
    if agent_ids is not None:
        _nodes[node_id].agent_ids = agent_ids
    return _nodes[node_id]


@router.delete("/{node_id}", status_code=204)
async def deregister_node(node_id: str):
    node = _nodes.pop(node_id, None)
    if node:
        await ws_manager.broadcast_notification({
            "type": "node_disconnected",
            "message": f"Node '{node_id}' disconnected",
            "data": {},
        })


# -----------------------------------------------------------------------
# Node configuration — push agent/chain config to a live node via Redis
# -----------------------------------------------------------------------

@router.post("/{node_id}/config", status_code=200)
async def configure_node(node_id: str, body: NodeConfigUpdate, request: Request):
    """
    Push a new agent/chain configuration to a running node.

    The master stores the config locally (for UI display) and publishes it
    to the Redis channel `config:{node_id}`.  The node worker subscribes to
    this channel and hot-reloads agents/chains without restarting.
    """
    if node_id not in _nodes:
        raise HTTPException(404, f"Node '{node_id}' not registered")

    # Persist config in master registry so UI can display it
    _nodes[node_id].agent_configs = body.agents
    _nodes[node_id].agent_ids = [a.get("name", a.get("id", "?")) for a in body.agents]

    # Publish to Redis for live reconfiguration
    redis = request.app.state.redis
    config_payload = {
        "type": "config_update",
        "agents": body.agents,
        "chains": body.chains,
        "allowed_tools": body.allowed_tools,
    }
    channel = f"config:{node_id}"
    try:
        await redis.publish(channel, json.dumps(config_payload))
        logger.info("Config update published to node '%s' (%d agents)", node_id, len(body.agents))
    except Exception as exc:
        logger.error("Failed to publish config to node '%s': %s", node_id, exc)
        raise HTTPException(502, f"Redis publish failed: {exc}")

    await ws_manager.broadcast_notification({
        "type": "node_config_updated",
        "message": f"Node '{node_id}' config updated ({len(body.agents)} agents)",
        "data": {"node_id": node_id, "agent_count": len(body.agents)},
    })

    return {
        "node_id": node_id,
        "agents_pushed": len(body.agents),
        "chains_pushed": len(body.chains),
    }


@router.get("/{node_id}/config", response_model=NodeConfigUpdate)
async def get_node_config(node_id: str):
    """Return the agent configs currently assigned to this node (master-side view)."""
    node = _nodes.get(node_id)
    if not node:
        raise HTTPException(404, f"Node '{node_id}' not registered")
    return NodeConfigUpdate(agents=node.agent_configs)


# -----------------------------------------------------------------------
# Task stats update (called internally from result subscriber)
# -----------------------------------------------------------------------

def record_task_result(node_id: str, status: str) -> None:
    """Update per-node task counters when a result arrives."""
    node = _nodes.get(node_id)
    if not node:
        return
    if status == "running":
        node.tasks_running = max(0, node.tasks_running + 1)
    elif status in ("completed", "failed", "cancelled"):
        node.tasks_running = max(0, node.tasks_running - 1)
        if status == "completed":
            node.tasks_completed += 1


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _evict_stale() -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=NODE_TIMEOUT_SECONDS)
    for nid, n in _nodes.items():
        if n.last_seen < cutoff:
            n.status = "offline"
