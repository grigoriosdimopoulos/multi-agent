"""
Node Worker — distributed execution agent.

Each node:
  1. Registers itself with the master REST API
  2. Subscribes to a Redis channel for incoming tasks
  3. Runs tasks using its local Orchestrator
  4. Publishes results back to the master channel
  5. Sends a heartbeat every N seconds

Run:
    python -m node.worker --config config/agents.yaml

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
from core.tools.registry import tool_registry
from core.security import verify_node_secret

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("node.worker")

NODE_ID            = os.getenv("NODE_ID", socket.gethostname())
NODE_HOST          = os.getenv("NODE_HOST", socket.gethostname())
NODE_PORT          = int(os.getenv("NODE_PORT", "8001"))
MASTER_URL         = os.getenv("MASTER_URL", "http://localhost:8000")
REDIS_URL          = os.getenv("REDIS_URL", "redis://localhost:6379")
AGENTS_CONFIG      = os.getenv("AGENTS_CONFIG", "./config/agents.yaml")
CHROMA_DIR         = os.getenv("CHROMA_DIR", "./data/chroma")
HEARTBEAT_SEC      = int(os.getenv("NODE_HEARTBEAT_SEC", "15"))
TASK_CHANNEL       = f"tasks:{NODE_ID}"
RESULT_CHANNEL     = "results"
BROADCAST_CHANNEL  = "tasks:broadcast"   # tasks sent to all nodes


# -----------------------------------------------------------------------
# Registration & heartbeat
# -----------------------------------------------------------------------

async def register_with_master(
    client: httpx.AsyncClient, agent_ids: list[str]
) -> bool:
    shared_secret = os.getenv("NODE_SHARED_SECRET", "")
    headers = {"X-Node-Secret": shared_secret} if shared_secret else {}
    payload = {
        "node_id": NODE_ID,
        "host": NODE_HOST,
        "port": NODE_PORT,
        "agent_ids": agent_ids,
        "capabilities": {"platform": os.uname().sysname},
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


async def heartbeat_loop(client: httpx.AsyncClient, agent_ids: list[str]) -> None:
    while True:
        try:
            await client.post(
                f"{MASTER_URL}/api/nodes/{NODE_ID}/heartbeat",
                json=agent_ids,
            )
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_SEC)


# -----------------------------------------------------------------------
# Task execution
# -----------------------------------------------------------------------

async def handle_task(
    task_payload: dict,
    orch: Orchestrator,
    redis: aioredis.Redis,
) -> None:
    task_id  = task_payload.get("task_id", str(uuid.uuid4()))
    input_   = task_payload.get("input", "")
    agent_id = task_payload.get("agent_id")
    chain_id = task_payload.get("chain_id")
    recursive = task_payload.get("recursive", False)

    logger.info("Running task %s (agent=%s chain=%s)", task_id, agent_id, chain_id)

    task = await orch.run_task(
        input_text=input_,
        agent_id=agent_id,
        chain_id=chain_id,
        recursive=recursive,
        task_id=task_id,
    )

    result_payload = {
        "node_id": NODE_ID,
        **task.to_dict(),
    }
    await redis.publish(RESULT_CHANNEL, json.dumps(result_payload))
    logger.info("Task %s → %s", task_id, task.status)


# -----------------------------------------------------------------------
# Redis subscriber loop
# -----------------------------------------------------------------------

async def subscriber_loop(orch: Orchestrator) -> None:
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(TASK_CHANNEL, BROADCAST_CHANNEL)
    logger.info(
        "Subscribed to channels: %s, %s", TASK_CHANNEL, BROADCAST_CHANNEL
    )

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            payload = json.loads(message["data"])
        except json.JSONDecodeError:
            continue

        # Verify node secret if present
        secret = payload.pop("node_secret", "")
        if not verify_node_secret(secret):
            logger.warning("Rejected task with invalid node secret")
            continue

        asyncio.create_task(handle_task(payload, orch, redis))


# -----------------------------------------------------------------------
# Main entry point
# -----------------------------------------------------------------------

async def main() -> None:
    # Build orchestrator from config
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
        asyncio.create_task(heartbeat_loop(client, agent_ids))
        await subscriber_loop(orch)


if __name__ == "__main__":
    asyncio.run(main())
