"""
FastAPI master server — the central control plane.

Startup:
    uvicorn master.api.main:app --host 0.0.0.0 --port 8000 --reload

The master server:
  - Exposes REST + WebSocket endpoints for the React frontend
  - Dispatches tasks to worker nodes via Redis (never runs tasks locally)
  - Receives results from worker nodes via Redis "results" channel
  - Loads agents from config/agents.yaml on startup (for chat / reference)
  - Serves the built React app at / in production
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Repo root — load .env before reading env vars
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_REPO_ROOT / ".env")

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from core.orchestrator import Orchestrator
from core.tools.registry import tool_registry
from .models import NotificationEvent
from .websocket_manager import ws_manager
from .routes.agents import router as agents_router, chains_router
from .routes.tasks import router as tasks_router
from .routes.knowledge import router as knowledge_router
from .routes.nodes import router as nodes_router, record_task_result
from .routes.chat import router as chat_router
from core.security import verify_api_key, rate_limiter, master_api_key_auth_enabled

logger = logging.getLogger(__name__)

AGENTS_CONFIG = os.getenv("AGENTS_CONFIG", "./config/agents.yaml")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REQUIRE_API_KEY = master_api_key_auth_enabled()
RESULT_CHANNEL = "results"


# -----------------------------------------------------------------------
# Result subscriber — listens for task completions from nodes
# -----------------------------------------------------------------------

async def _result_subscriber(app: FastAPI, redis: aioredis.Redis) -> None:
    """Background task: subscribe to 'results' channel, update registry, broadcast."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(RESULT_CHANNEL)
    logger.info("Master subscribed to Redis channel '%s'", RESULT_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            result: dict = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            continue

        task_id = result.get("task_id")
        node_id = result.get("node_id", "")
        status = result.get("status", "")

        # Update master task registry
        registry: dict = app.state.task_registry
        if task_id and task_id in registry:
            registry[task_id].update({
                k: result[k]
                for k in ("status", "output", "error", "completed_at", "iterations", "subtask_ids")
                if k in result
            })
            if node_id:
                registry[task_id]["node_id"] = node_id

        # Update per-node counters
        if node_id:
            record_task_result(node_id, status)

        # Broadcast update to all WebSocket clients
        await ws_manager.broadcast_task_update(result)

        # Send a notification for terminal states
        if status == "completed":
            await ws_manager.broadcast_notification({
                "type": "task_completed",
                "message": f"Task {task_id[:8]}… completed on node '{node_id}'",
                "data": result,
            })
        elif status == "failed":
            await ws_manager.broadcast_notification({
                "type": "task_failed",
                "message": f"Task {task_id[:8]}… failed on node '{node_id}': {result.get('error', '')}",
                "data": result,
            })


# -----------------------------------------------------------------------
# Lifespan (startup / shutdown)
# -----------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Redis ----
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.state.redis = redis

    # ---- Task registry (master-side) ----
    app.state.task_registry: dict[str, dict] = {}

    # ---- Orchestrator (used only for chat / reference agents) ----
    orch = Orchestrator(registry=tool_registry)

    async def _on_task(task):
        await ws_manager.broadcast_task_update(task.to_dict())
    orch.on_task_update(_on_task)

    # Load agents from YAML (for chat endpoint — not for dispatched tasks)
    cfg_path = Path(AGENTS_CONFIG)
    if cfg_path.exists():
        with cfg_path.open() as fh:
            config = yaml.safe_load(fh) or {}
        for agent_cfg in config.get("agents", []):
            try:
                agent = orch.create_agent_from_config(agent_cfg)
                orch.register_agent(agent)
                logger.info("Loaded agent '%s' from config", agent.name)
            except Exception as exc:
                logger.warning("Failed to load agent '%s': %s", agent_cfg.get("name"), exc)

        for chain_cfg in config.get("chains", []):
            try:
                chain = orch.create_chain_from_config(chain_cfg)
                orch.register_chain(chain)
            except Exception as exc:
                logger.warning("Failed to load chain: %s", exc)

    app.state.orchestrator = orch
    logger.info("Master API ready. Chat agents: %d", len(orch.agents))

    # ---- Start result subscriber in background ----
    subscriber_task = asyncio.create_task(_result_subscriber(app, redis))

    yield

    # ---- Shutdown ----
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
    await redis.aclose()
    logger.info("Master API shutdown complete")


# -----------------------------------------------------------------------
# App
# -----------------------------------------------------------------------

app = FastAPI(
    title="Multi-Agent AI System",
    description="Distributed multi-agent AI with configurable LLM providers",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server + same-origin production
allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173,"
    "http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------
# Security middleware
# -----------------------------------------------------------------------

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    _public = ("/health", "/api/health", "/docs", "/openapi.json")
    if REQUIRE_API_KEY and request.url.path not in _public:
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key", "")
        if not verify_api_key(key):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

app.include_router(agents_router,    prefix="/api")
app.include_router(chains_router,    prefix="/api")
app.include_router(tasks_router,     prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(nodes_router,     prefix="/api")
app.include_router(chat_router,      prefix="/api")


@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "agents": len(app.state.orchestrator.agents),
        "tasks_tracked": len(app.state.task_registry),
        "ws_connections": ws_manager.count(),
        "api_key_required": master_api_key_auth_enabled(),
    }


# -----------------------------------------------------------------------
# WebSocket endpoint
# -----------------------------------------------------------------------

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await ws_manager.send(session_id, {"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)


# -----------------------------------------------------------------------
# Serve React frontend (production build)
# -----------------------------------------------------------------------

frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
