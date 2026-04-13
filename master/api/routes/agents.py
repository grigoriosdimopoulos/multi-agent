"""Agent CRUD routes."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request

from ..models import AgentCreateRequest, AgentResponse, ChainCreateRequest, ChainResponse
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/agents", tags=["agents"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.get("/", response_model=list[AgentResponse])
async def list_agents(orch=Depends(get_orchestrator)):
    return [
        AgentResponse(
            id=info["id"],
            name=info["name"],
            description=info.get("description", ""),
            provider=info["provider"],
            tools=info["tools"],
            privilege_level=info.get("privilege_level", 1),
            tags=info.get("tags", []),
        )
        for info in orch.get_agent_infos()
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, orch=Depends(get_orchestrator)):
    agent = orch.agents.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    info = agent.get_info()
    return AgentResponse(
        id=info["id"],
        name=info["name"],
        description=info.get("description", ""),
        provider=info["provider"],
        tools=info["tools"],
        privilege_level=info.get("privilege_level", 1),
        tags=info.get("tags", []),
    )


@router.post("/", response_model=AgentResponse, status_code=201)
async def create_agent(body: AgentCreateRequest, orch=Depends(get_orchestrator)):
    cfg = body.model_dump()
    cfg["id"] = str(uuid.uuid4())
    # Flatten provider
    cfg["provider"] = body.provider.model_dump()
    agent = orch.create_agent_from_config(cfg)
    orch.register_agent(agent)
    info = agent.get_info()
    await ws_manager.broadcast_agent_update(info, action="created")
    return AgentResponse(
        id=info["id"],
        name=info["name"],
        description=info.get("description", ""),
        provider=info["provider"],
        tools=info["tools"],
        privilege_level=info.get("privilege_level", 1),
        tags=info.get("tags", []),
    )


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, orch=Depends(get_orchestrator)):
    if agent_id not in orch.agents:
        raise HTTPException(404, f"Agent '{agent_id}' not found")
    orch.unregister_agent(agent_id)
    await ws_manager.broadcast_agent_update({"id": agent_id}, action="deleted")


# -----------------------------------------------------------------------
# Chain sub-routes
# -----------------------------------------------------------------------

chains_router = APIRouter(prefix="/chains", tags=["chains"])


@chains_router.get("/", response_model=list[ChainResponse])
async def list_chains(orch=Depends(get_orchestrator)):
    return [
        ChainResponse(chain_id=c["chain_id"], mode=c["mode"], steps=c["steps"])
        for c in orch.get_chain_infos()
    ]


@chains_router.post("/", response_model=ChainResponse, status_code=201)
async def create_chain(body: ChainCreateRequest, orch=Depends(get_orchestrator)):
    cfg = body.model_dump()
    chain = orch.create_chain_from_config(cfg)
    orch.register_chain(chain)
    info = chain.get_info()
    return ChainResponse(chain_id=info["chain_id"], mode=info["mode"], steps=info["steps"])
