"""
FastAPI master server — the central control plane.

Startup:
    uvicorn master.api.main:app --host 0.0.0.0 --port 8000 --reload

The master server:
  - Exposes REST + WebSocket endpoints for the React frontend
  - Holds an Orchestrator instance (or can proxy tasks to worker nodes via Redis)
  - Loads agents from config/agents.yaml on startup
  - Serves the built React app at / in production
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
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
from .routes.nodes import router as nodes_router
from .routes.chat import router as chat_router
from core.security import verify_api_key, rate_limiter

logger = logging.getLogger(__name__)

AGENTS_CONFIG = os.getenv("AGENTS_CONFIG", "./config/agents.yaml")
REQUIRE_API_KEY = os.getenv("MASTER_API_KEYS", "") != ""


# -----------------------------------------------------------------------
# Lifespan (startup / shutdown)
# -----------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    orch = Orchestrator(registry=tool_registry)

    # Register task-update callback → broadcast to WebSocket clients
    async def _on_task(task):
        await ws_manager.broadcast_task_update(task.to_dict())
    orch.on_task_update(_on_task)

    # Load agents from YAML
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
    logger.info("Master API ready. Agents: %d", len(orch.agents))

    yield

    # ---- Shutdown ----
    logger.info("Master API shutting down")


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
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------
# Security middleware
# -----------------------------------------------------------------------

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Rate limiting (by IP)
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    # API key check (skip WebSocket + health)
    if REQUIRE_API_KEY and request.url.path not in ("/health", "/docs", "/openapi.json"):
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key", "")
        if not verify_api_key(key):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

    return await call_next(request)


# -----------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------

app.include_router(agents_router, prefix="/api")
app.include_router(chains_router, prefix="/api")
app.include_router(tasks_router,  prefix="/api")
app.include_router(knowledge_router, prefix="/api")
app.include_router(nodes_router,  prefix="/api")
app.include_router(chat_router,   prefix="/api")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents": len(app.state.orchestrator.agents),
        "ws_connections": ws_manager.count(),
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
            # Handle ping
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
