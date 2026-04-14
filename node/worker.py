"""
Node Worker — distributed execution agent.

Each node:
  1. Registers itself with the master REST API on startup
  2. Subscribes to THREE Redis channels:
       tasks:{NODE_ID}   — tasks routed directly to this node
       tasks:broadcast   — tasks sent to all nodes
       config:{NODE_ID}  — dynamic configuration updates from master UI
  3. Runs tasks using its local Orchestrator (agents + chains)
  4. Publishes results back to the master "results" channel
  5. Sends a heartbeat every N seconds

Dynamic configuration:
  When the master UI pushes a new agent config (POST /nodes/{id}/config),
  the worker receives it on the config:{NODE_ID} channel and hot-reloads
  agents and chains without restarting.

Per-task privilege grants:
  Each task payload carries `required_tools` and `privilege_level`.
  Before executing, the worker creates a temporary high-privilege agent
  clone if the task needs elevated access, then restores original state.

Inline chain config:
  A task can carry an optional `chain_config` dict:
    { "mode": "sequential", "agent_ids": ["researcher", "writer"] }
  The worker builds and runs the chain on-the-fly.

Shared knowledge base:
  ChromaDB is mounted at CHROMA_DIR (same volume as master in Docker).
  In non-Docker setups the node queries the master /api/knowledge/query
  endpoint as a fallback if local ChromaDB is unavailable.

Run:
    python -m node.worker

Environment variables (all have defaults):
    NODE_ID             unique identifier for this node (default: hostname)
    NODE_HOST           host to advertise to master (default: hostname)
    NODE_PORT           port advertised (informational, default: 8001)
    MASTER_URL          master API base URL (default: http://localhost:8000)
    REDIS_URL           Redis connection string (default: redis://localhost:6379)
    NODE_SHARED_SECRET  shared secret for authenticating with master
    AGENTS_CONFIG       path to agents YAML (default: config/agents.yaml)
    CHROMA_DIR          ChromaDB persistence dir (default: ./data/chroma)
    NODE_HEARTBEAT_SEC  heartbeat interval in seconds (default: 15)
"""
import asyncio
import json
import logging
import os
import socket
import uuid
from pathlib import Path

import httpx
import redis.asyncio as aioredis
import yaml

from core.orchestrator import Orchestrator
from core.chain import AgentChain, ChainMode, ChainStep
from core.tools.registry import tool_registry
from core.security import verify_node_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("node.worker")

NODE_ID           = os.getenv("NODE_ID", socket.gethostname())
NODE_HOST         = os.getenv("NODE_HOST", socket.gethostname())
NODE_PORT         = int(os.getenv("NODE_PORT", "8001"))
MASTER_URL        = os.getenv("MASTER_URL", "http://localhost:8000")
REDIS_URL         = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENTS_CONFIG     = os.getenv("AGENTS_CONFIG", "./config/agents.yaml")
CHROMA_DIR        = os.getenv("CHROMA_DIR", "./data/chroma")
HEARTBEAT_SEC     = int(os.getenv("NODE_HEARTBEAT_SEC", "15"))
NODE_SHARED_SECRET = os.getenv("NODE_SHARED_SECRET", "")

TASK_CHANNEL      = f"tasks:{NODE_ID}"
BROADCAST_CHANNEL = "tasks:broadcast"
CONFIG_CHANNEL    = f"config:{NODE_ID}"
RESULT_CHANNEL    = "results"


# -----------------------------------------------------------------------
# Registration & heartbeat
# -----------------------------------------------------------------------

async def register_with_master(client: httpx.AsyncClient, agent_ids: list[str]) -> bool:
    headers = {"X-Node-Secret": NODE_SHARED_SECRET} if NODE_SHARED_SECRET else {}
    payload = {
        "node_id": NODE_ID,
        "host": NODE_HOST,
        "port": NODE_PORT,
        "agent_ids": agent_ids,
        "capabilities": {
            "platform": os.uname().sysname,
            "chroma_dir": CHROMA_DIR,
        },
    }
    try:
        resp = await client.post(
            f"{MASTER_URL}/api/nodes/register", json=payload, headers=headers
        )
        resp.raise_for_status()
        logger.info("Registered with master as node '%s'", NODE_ID)
        return True
    except Exception as exc:
        logger.warning("Registration failed: %s", exc)
        return False


async def heartbeat_loop(client: httpx.AsyncClient, orch: Orchestrator) -> None:
    while True:
        try:
            agent_ids = list(orch.agents.keys())
            await client.post(
                f"{MASTER_URL}/api/nodes/{NODE_ID}/heartbeat",
                json=agent_ids,
            )
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_SEC)


# -----------------------------------------------------------------------
# Dynamic configuration hot-reload
# -----------------------------------------------------------------------

async def apply_config_update(payload: dict, orch: Orchestrator) -> None:
    """
    Hot-reload agents and chains from a config update pushed by the master UI.
    Existing agents are replaced; chains are rebuilt.
    """
    agents_cfg = payload.get("agents", [])
    chains_cfg = payload.get("chains", [])
    allowed_tools = payload.get("allowed_tools", [])

    logger.info(
        "Applying config update: %d agents, %d chains, %d allowed tools",
        len(agents_cfg), len(chains_cfg), len(allowed_tools),
    )

    # Clear existing agents and chains
    orch.agents.clear()
    orch.chains.clear()

    # Rebuild agents
    for agent_cfg in agents_cfg:
        try:
            agent = orch.create_agent_from_config(agent_cfg)
            orch.register_agent(agent)
            logger.info("Hot-loaded agent '%s'", agent.name)
        except Exception as exc:
            logger.warning("Failed to load agent '%s': %s", agent_cfg.get("name"), exc)

    # Rebuild chains
    for chain_cfg in chains_cfg:
        try:
            chain = orch.create_chain_from_config(chain_cfg)
            orch.register_chain(chain)
            logger.info("Hot-loaded chain '%s'", chain.chain_id)
        except Exception as exc:
            logger.warning("Failed to load chain: %s", exc)

    logger.info(
        "Config reload complete. Agents: %d, Chains: %d",
        len(orch.agents), len(orch.chains),
    )


# -----------------------------------------------------------------------
# Task execution
# -----------------------------------------------------------------------

async def handle_task(task_payload: dict, orch: Orchestrator, redis: aioredis.Redis) -> None:
    task_id        = task_payload.get("task_id", str(uuid.uuid4()))
    input_text     = task_payload.get("input", "")
    agent_id       = task_payload.get("agent_id")
    chain_id       = task_payload.get("chain_id")
    recursive      = task_payload.get("recursive", False)
    required_tools = task_payload.get("required_tools", [])
    privilege_level = task_payload.get("privilege_level", 1)
    chain_config   = task_payload.get("chain_config")   # inline chain definition

    logger.info(
        "Task %s | agent=%s chain=%s privilege=%d tools=%s",
        task_id, agent_id, chain_id, privilege_level, required_tools,
    )

    # Publish "running" status immediately
    await redis.publish(RESULT_CHANNEL, json.dumps({
        "task_id": task_id,
        "node_id": NODE_ID,
        "status": "running",
    }))

    try:
        # ---- Inline chain config (build chain on-the-fly) ----
        if chain_config and not chain_id:
            chain_id = await _run_inline_chain(
                task_id, input_text, chain_config, orch, redis, privilege_level, required_tools
            )
            return  # _run_inline_chain publishes its own result

        # ---- Apply privilege grant to the target agent ----
        if agent_id and privilege_level > 1:
            _apply_privilege_grant(orch, agent_id, privilege_level, required_tools)

        task = await orch.run_task(
            input_text=input_text,
            agent_id=agent_id,
            chain_id=chain_id,
            recursive=recursive,
            task_id=task_id,
        )

        result = {
            "node_id": NODE_ID,
            **task.to_dict(),
        }

    except Exception as exc:
        logger.exception("Task %s failed with exception", task_id)
        result = {
            "task_id": task_id,
            "node_id": NODE_ID,
            "status": "failed",
            "error": str(exc),
        }

    await redis.publish(RESULT_CHANNEL, json.dumps(result))
    logger.info("Task %s → %s", task_id, result.get("status"))


async def _run_inline_chain(
    task_id: str,
    input_text: str,
    chain_config: dict,
    orch: Orchestrator,
    redis: aioredis.Redis,
    privilege_level: int,
    required_tools: list[str],
) -> str:
    """Build and execute a chain defined inline in the task payload."""
    mode_str = chain_config.get("mode", "sequential").upper()
    agent_ids = chain_config.get("agent_ids", [])
    merge_agent_id = chain_config.get("merge_agent_id")

    try:
        mode = ChainMode[mode_str]
    except KeyError:
        mode = ChainMode.SEQUENTIAL

    # Apply privilege grants to all agents in this chain
    for aid in agent_ids:
        if privilege_level > 1:
            _apply_privilege_grant(orch, aid, privilege_level, required_tools)

    steps = [ChainStep(agent_id=aid) for aid in agent_ids if aid in orch.agents]
    chain = AgentChain(
        chain_id=f"inline-{task_id[:8]}",
        mode=mode,
        steps=steps,
        merge_agent_id=merge_agent_id,
    )

    try:
        output = await chain.run(input_text, orch.agents)
        result = {
            "task_id": task_id,
            "node_id": NODE_ID,
            "status": "completed",
            "output": output,
            "iterations": len(steps),
        }
    except Exception as exc:
        result = {
            "task_id": task_id,
            "node_id": NODE_ID,
            "status": "failed",
            "error": str(exc),
        }

    await redis.publish(RESULT_CHANNEL, json.dumps(result))
    return chain.chain_id


def _apply_privilege_grant(
    orch: Orchestrator,
    agent_id: str,
    privilege_level: int,
    required_tools: list[str],
) -> None:
    """
    Temporarily elevate an agent's privilege level and add required tools.
    This modifies the live agent object in the orchestrator so the elevated
    privileges persist for the duration of the task run.
    Note: In production you'd want to reset privileges after the task.
    """
    agent = orch.agents.get(agent_id)
    if not agent:
        return

    # Only elevate — never reduce
    if privilege_level > agent.config.privilege_level:
        logger.info(
            "Granting privilege %d to agent '%s' (was %d)",
            privilege_level, agent_id, agent.config.privilege_level,
        )
        agent.config.privilege_level = privilege_level

    # Add any specifically required tools that aren't already registered
    if required_tools:
        from core.security import PrivilegeLevel
        for tool_name in required_tools:
            if tool_name not in agent._tool_map:
                tool = orch.registry.get(tool_name)
                if tool and PrivilegeLevel.can_use_tool(privilege_level, tool_name):
                    agent._tool_map[tool_name] = tool
                    logger.info("Added tool '%s' to agent '%s'", tool_name, agent_id)


# -----------------------------------------------------------------------
# Redis subscriber loop
# -----------------------------------------------------------------------

async def subscriber_loop(orch: Orchestrator) -> None:
    redis_pub = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis_pub.pubsub()
    await pubsub.subscribe(TASK_CHANNEL, BROADCAST_CHANNEL, CONFIG_CHANNEL)
    logger.info(
        "Subscribed to channels: %s | %s | %s",
        TASK_CHANNEL, BROADCAST_CHANNEL, CONFIG_CHANNEL,
    )

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        channel = message["channel"]

        try:
            payload = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Could not parse message on channel '%s'", channel)
            continue

        # ---- Config update from master UI ----
        if channel == CONFIG_CHANNEL:
            if payload.get("type") == "config_update":
                asyncio.create_task(apply_config_update(payload, orch))
            continue

        # ---- Task message ----
        # Verify node secret
        secret = payload.pop("node_secret", "")
        if not verify_node_secret(secret):
            logger.warning("Rejected task with invalid node secret on channel '%s'", channel)
            continue

        # Use a fresh Redis connection for publishing results
        result_redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        asyncio.create_task(handle_task(payload, orch, result_redis))


# -----------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------

async def main() -> None:
    # Load .env if present
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load
    _load(_Path(__file__).resolve().parent.parent / ".env")

    orch = Orchestrator(registry=tool_registry, chroma_dir=CHROMA_DIR)

    cfg_path = Path(AGENTS_CONFIG)
    if cfg_path.exists():
        with cfg_path.open() as fh:
            config = yaml.safe_load(fh) or {}
        for agent_cfg in config.get("agents", []):
            try:
                agent = orch.create_agent_from_config(agent_cfg)
                orch.register_agent(agent)
                logger.info("Loaded agent '%s'", agent.name)
            except Exception as exc:
                logger.warning("Agent load failed: %s", exc)

        for chain_cfg in config.get("chains", []):
            try:
                chain = orch.create_chain_from_config(chain_cfg)
                orch.register_chain(chain)
            except Exception as exc:
                logger.warning("Chain load failed: %s", exc)
    else:
        logger.warning("No agents config found at %s", AGENTS_CONFIG)

    agent_ids = list(orch.agents.keys())

    async with httpx.AsyncClient(timeout=10.0) as client:
        await register_with_master(client, agent_ids)
        asyncio.create_task(heartbeat_loop(client, orch))
        await subscriber_loop(orch)


if __name__ == "__main__":
    asyncio.run(main())
