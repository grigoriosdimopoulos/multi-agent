"""Pydantic request / response models for the master API."""
import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------
# Provider / Agent
# -----------------------------------------------------------------------

class ProviderConfig(BaseModel):
    type: str                       # ollama | openai | anthropic | groq
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    provider: ProviderConfig
    tools: list[str] = []
    system_prompt: str = "You are a helpful AI assistant."
    temperature: float = 0.7
    max_tokens: int = 4096
    privilege_level: int = 1        # 0=READ_ONLY 1=STANDARD 2=ELEVATED 3=ADMIN
    knowledge_collection: Optional[str] = None
    tags: list[str] = []


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    provider: dict
    tools: list[str]
    privilege_level: int
    tags: list[str]
    status: str = "active"


# -----------------------------------------------------------------------
# Chain
# -----------------------------------------------------------------------

class ChainCreateRequest(BaseModel):
    chain_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    mode: str = "sequential"        # sequential | parallel | router
    agent_ids: list[str]
    merge_agent_id: Optional[str] = None


class ChainResponse(BaseModel):
    chain_id: str
    mode: str
    steps: list[str]


# -----------------------------------------------------------------------
# Task
# -----------------------------------------------------------------------

class TaskCreateRequest(BaseModel):
    input: str
    agent_id: Optional[str] = None
    chain_id: Optional[str] = None
    node_id: Optional[str] = None        # target node (None = broadcast to all)
    recursive: bool = False
    required_tools: list[str] = []       # tools the node must enable for this task
    privilege_level: int = 1             # privilege level granted to agent for this task
    prerequisites: list[str] = []       # task_ids that must complete before this runs
    chain_config: Optional[dict] = None  # inline chain: {mode, agent_ids, merge_agent_id}


class TaskResponse(BaseModel):
    task_id: str
    status: str
    agent_id: Optional[str] = None
    chain_id: Optional[str] = None
    node_id: Optional[str] = None
    input: str
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: str                      # ISO string (simpler for cross-process sharing)
    completed_at: Optional[str] = None
    iterations: int = 0
    subtask_ids: list[str] = []
    required_tools: list[str] = []
    privilege_level: int = 1


# -----------------------------------------------------------------------
# Chat
# -----------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str
    agent_id: Optional[str] = None
    chain_id: Optional[str] = None
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stream: bool = True


# -----------------------------------------------------------------------
# Knowledge
# -----------------------------------------------------------------------

class KnowledgeQueryRequest(BaseModel):
    query: str
    collection: str = "default"
    n_results: int = 5


class KnowledgeCollectionInfo(BaseModel):
    name: str
    count: int


# -----------------------------------------------------------------------
# Node registry
# -----------------------------------------------------------------------

class NodeRegisterRequest(BaseModel):
    node_id: str
    host: str
    port: int
    capabilities: dict = {}
    agent_ids: list[str] = []


class NodeInfo(BaseModel):
    node_id: str
    host: str
    port: int
    status: str = "active"
    agent_ids: list[str] = []
    agent_configs: list[dict] = []       # full agent config objects stored at master
    capabilities: dict = {}
    last_seen: datetime = Field(default_factory=datetime.utcnow)
    tasks_completed: int = 0
    tasks_running: int = 0


class NodeConfigUpdate(BaseModel):
    """Sent via Redis to dynamically reconfigure a node."""
    agents: list[dict] = []             # list of agent config dicts (same format as agents.yaml)
    chains: list[dict] = []             # list of chain config dicts
    allowed_tools: list[str] = []       # restrict available tools on this node


# -----------------------------------------------------------------------
# Notifications / WebSocket events
# -----------------------------------------------------------------------

class NotificationEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str   # task_completed | task_failed | agent_error | node_disconnected | info
    message: str
    data: dict = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)
