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
    node_id: Optional[str] = None   # target node (None = any available)
    recursive: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: str
    agent_id: Optional[str] = None
    chain_id: Optional[str] = None
    input: str
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    iterations: int = 0
    subtask_ids: list[str] = []


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
    capabilities: dict = {}
    last_seen: datetime = Field(default_factory=datetime.utcnow)


# -----------------------------------------------------------------------
# Notifications / WebSocket events
# -----------------------------------------------------------------------

class NotificationEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str   # task_completed | task_failed | agent_error | node_disconnected | info
    message: str
    data: dict = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)
