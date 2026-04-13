"""
Orchestrator — manages agents and chains, dispatches tasks, fires callbacks.

Each node (laptop / server) runs one Orchestrator instance.
The master API creates tasks and forwards them to the correct node's
Orchestrator via Redis.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from .agent import Agent, AgentConfig, AgentResult
from .chain import AgentChain, ChainMode, ChainResult
from .providers import create_provider
from .security import PrivilegeLevel
from .tools.knowledge_tools import QueryKnowledgeBaseTool
from .tools.registry import ToolRegistry, tool_registry


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Task model
# -----------------------------------------------------------------------

@dataclass
class TaskStatus:
    task_id: str
    status: str           # pending | running | completed | failed
    agent_id: Optional[str] = None
    chain_id: Optional[str] = None
    input: str = ""
    output: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    iterations: int = 0
    recursive: bool = False
    subtask_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "agent_id": self.agent_id,
            "chain_id": self.chain_id,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "iterations": self.iterations,
            "recursive": self.recursive,
            "subtask_ids": self.subtask_ids,
        }


# -----------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------

class Orchestrator:
    """
    Coordinates agents and chains on a single node.

    Usage
    -----
    orch = Orchestrator()
    orch.register_agent(my_agent)
    task = await orch.run_task("Summarise the sales report", agent_id="sales-agent")
    print(task.output)
    """

    def __init__(
        self,
        registry: ToolRegistry = tool_registry,
        chroma_dir: str = "./data/chroma",
    ) -> None:
        self.registry = registry
        self.chroma_dir = chroma_dir
        self.agents: dict[str, Agent] = {}
        self.chains: dict[str, AgentChain] = {}
        self.tasks: dict[str, TaskStatus] = {}
        self._callbacks: list[Callable] = []
        self._log = logging.getLogger("orchestrator")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(self, agent: Agent) -> None:
        self.agents[agent.id] = agent
        self._log.info("Registered agent '%s' (%s)", agent.name, agent.id)

    def unregister_agent(self, agent_id: str) -> None:
        self.agents.pop(agent_id, None)

    def register_chain(self, chain: AgentChain) -> None:
        self.chains[chain.chain_id] = chain
        self._log.info("Registered chain '%s'", chain.chain_id)

    # ------------------------------------------------------------------
    # Dynamic agent creation from YAML / API config dict
    # ------------------------------------------------------------------

    def create_agent_from_config(self, cfg: dict) -> Agent:
        """
        Build an Agent from a plain dict (e.g. loaded from agents.yaml).

        Required keys: name, provider.type, provider.model
        Optional: tools, system_prompt, temperature, privilege_level, description
        """
        prov_cfg = cfg["provider"]
        provider = create_provider(
            provider_type=prov_cfg["type"],
            model=prov_cfg.get("model", ""),
            api_key=prov_cfg.get("api_key"),
            base_url=prov_cfg.get("base_url"),
        )

        tool_names: list[str] = cfg.get("tools", [])
        tools = self.registry.get_many(tool_names)

        # Inject knowledge retrieval function if requested
        kb_collection = cfg.get("knowledge_collection")
        if kb_collection:
            from .knowledge.retrieval import retrieve

            async def _retrieve(**kw):
                return await retrieve(persist_directory=self.chroma_dir, **kw)

            kb_tool = QueryKnowledgeBaseTool(retrieval_fn=_retrieve)
            tools.append(kb_tool)

        agent_cfg = AgentConfig(
            agent_id=cfg.get("id", str(uuid.uuid4())),
            name=cfg["name"],
            description=cfg.get("description", ""),
            provider=provider,
            tools=tools,
            system_prompt=cfg.get(
                "system_prompt", "You are a helpful AI assistant."
            ),
            max_iterations=cfg.get("max_iterations", 10),
            temperature=cfg.get("temperature", 0.7),
            max_tokens=cfg.get("max_tokens", 4096),
            privilege_level=cfg.get("privilege_level", PrivilegeLevel.STANDARD),
            knowledge_collection=kb_collection,
            tags=cfg.get("tags", []),
        )
        return Agent(agent_cfg)

    def create_chain_from_config(self, cfg: dict) -> AgentChain:
        """Build an AgentChain from a config dict."""
        chain = AgentChain(
            chain_id=cfg.get("chain_id", str(uuid.uuid4())),
            mode=ChainMode(cfg.get("mode", "sequential")),
        )
        for agent_id in cfg.get("agent_ids", []):
            agent = self.agents.get(agent_id)
            if agent:
                chain.add_step(agent)
        return chain

    # ------------------------------------------------------------------
    # Task callbacks
    # ------------------------------------------------------------------

    def on_task_update(self, callback: Callable) -> None:
        """Register a callback called on every task status change."""
        self._callbacks.append(callback)

    async def _notify(self, task: TaskStatus) -> None:
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(task)
                else:
                    cb(task)
            except Exception as exc:
                self._log.error("Callback error: %s", exc)

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    async def run_task(
        self,
        input_text: str,
        agent_id: Optional[str] = None,
        chain_id: Optional[str] = None,
        recursive: bool = False,
        task_id: Optional[str] = None,
    ) -> TaskStatus:
        task_id = task_id or str(uuid.uuid4())
        task = TaskStatus(
            task_id=task_id,
            status="running",
            agent_id=agent_id,
            chain_id=chain_id,
            input=input_text,
            recursive=recursive,
        )
        self.tasks[task_id] = task
        await self._notify(task)

        try:
            if chain_id and chain_id in self.chains:
                result: ChainResult = await self.chains[chain_id].run(input_text)
                task.output = result.final_output
                task.status = "completed" if result.success else "failed"
                task.error = result.error

            elif agent_id and agent_id in self.agents:
                agent_result: AgentResult = await self.agents[agent_id].run(input_text)
                task.output = agent_result.content
                task.status = "completed" if agent_result.success else "failed"
                task.error = agent_result.error
                task.iterations = agent_result.iterations

                if recursive and agent_result.success:
                    await self._handle_recursive(task, agent_result)

            elif self.agents:
                # Auto-select first available agent
                fallback = next(iter(self.agents.values()))
                task.agent_id = fallback.id
                agent_result = await fallback.run(input_text)
                task.output = agent_result.content
                task.status = "completed" if agent_result.success else "failed"
                task.error = agent_result.error
                task.iterations = agent_result.iterations

            else:
                task.status = "failed"
                task.error = "No agents available on this node"

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            self._log.error("Task %s failed: %s", task_id, exc, exc_info=True)

        task.completed_at = datetime.utcnow()
        await self._notify(task)
        return task

    async def _handle_recursive(
        self, parent: TaskStatus, result: AgentResult
    ) -> None:
        """Parse SUBTASK: lines from the result and enqueue them."""
        subtasks = [
            line.replace("SUBTASK:", "").strip()
            for line in result.content.splitlines()
            if line.strip().startswith("SUBTASK:")
        ]
        for sub_input in subtasks[:5]:          # cap at 5 automatic subtasks
            sub = await self.run_task(
                input_text=sub_input,
                agent_id=parent.agent_id,
                task_id=str(uuid.uuid4()),
            )
            parent.subtask_ids.append(sub.task_id)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[TaskStatus]:
        return self.tasks.get(task_id)

    def list_tasks(self, status: Optional[str] = None) -> list[TaskStatus]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def get_agent_infos(self) -> list[dict]:
        return [a.get_info() for a in self.agents.values()]

    def get_chain_infos(self) -> list[dict]:
        return [c.get_info() for c in self.chains.values()]
