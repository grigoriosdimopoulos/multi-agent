"""Node registry routes — register, heartbeat, list distributed worker nodes."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models import NodeInfo, NodeRegisterRequest
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/nodes", tags=["nodes"])

# In-memory node registry (replace with Redis for production HA)
_nodes: dict[str, NodeInfo] = {}

NODE_TIMEOUT_SECONDS = 30


@router.get("/", response_model=list[NodeInfo])
async def list_nodes():
    _evict_stale()
    return list(_nodes.values())


@router.post("/register", response_model=NodeInfo, status_code=201)
async def register_node(body: NodeRegisterRequest):
    info = NodeInfo(
        node_id=body.node_id,
        host=body.host,
        port=body.port,
        status="active",
        agent_ids=body.agent_ids,
        capabilities=body.capabilities,
        last_seen=datetime.utcnow(),
    )
    _nodes[body.node_id] = info
    await ws_manager.broadcast_notification(
        {"type": "node_connected", "message": f"Node '{body.node_id}' connected", "data": info.model_dump(mode="json")}
    )
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
        await ws_manager.broadcast_notification(
            {"type": "node_disconnected", "message": f"Node '{node_id}' disconnected", "data": {}}
        )


def _evict_stale() -> None:
    cutoff = datetime.utcnow() - timedelta(seconds=NODE_TIMEOUT_SECONDS)
    stale = [nid for nid, n in _nodes.items() if n.last_seen < cutoff]
    for nid in stale:
        _nodes[nid].status = "offline"
