"""
Agent — ReAct (Reason + Act + Observe) execution loop.

Each agent has:
  - One LLM provider  (configurable per agent)
  - A list of tools   (subset of the global ToolRegistry)
  - A ConversationMemory
  - A privilege level (controls which tools are actually callable)
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional

from .memory import ConversationMemory
from .providers.base import BaseLLMProvider, Message
from .security import PrivilegeLevel, redact_secrets
from .tools.base import BaseTool, ToolResult


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------
# Configuration dataclass
# -----------------------------------------------------------------------

@dataclass
class AgentConfig:
    agent_id: str
    name: str
    provider: BaseLLMProvider
    tools: list[BaseTool] = field(default_factory=list)
    system_prompt: str = "You are a helpful AI assistant."
    max_iterations: int = 10
    temperature: float = 0.7
    max_tokens: int = 4096
    privilege_level: int = PrivilegeLevel.STANDARD
    knowledge_collection: Optional[str] = None
    # Metadata for the registry / API
    tags: list[str] = field(default_factory=list)
    description: str = ""


# -----------------------------------------------------------------------
# Result dataclass
# -----------------------------------------------------------------------

@dataclass
class AgentResult:
    agent_id: str
    agent_name: str
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    iterations: int = 0
    success: bool = True
    error: Optional[str] = None


# -----------------------------------------------------------------------
# Agent class
# -----------------------------------------------------------------------

class Agent:
    """
    ReAct-style agent.

    The main loop:
      1. Send messages + tool schemas to the LLM.
      2. If the LLM returns tool calls → execute them, append results, loop.
      3. If the LLM returns plain text → that is the final answer.
    """

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.memory = ConversationMemory(system_prompt=config.system_prompt)
        self._tool_map: dict[str, BaseTool] = {}
        for tool in config.tools:
            if PrivilegeLevel.can_use_tool(config.privilege_level, tool.name):
                self._tool_map[tool.name] = tool
        self._log = logging.getLogger(f"agent.{config.agent_id}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def id(self) -> str:
        return self.config.agent_id

    @property
    def name(self) -> str:
        return self.config.name

    # ------------------------------------------------------------------
    # Tool management
    # ------------------------------------------------------------------

    def add_tool(self, tool: BaseTool) -> None:
        if PrivilegeLevel.can_use_tool(self.config.privilege_level, tool.name):
            self.config.tools.append(tool)
            self._tool_map[tool.name] = tool

    def remove_tool(self, name: str) -> None:
        self._tool_map.pop(name, None)
        self.config.tools = [t for t in self.config.tools if t.name != name]

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> AgentResult:
        """Run the ReAct loop and return a final AgentResult."""
        self.memory.add("user", user_message)
        tool_schemas = [t.schema for t in self._tool_map.values()]
        all_tool_calls: list[dict] = []
        iterations = 0

        try:
            while iterations < self.config.max_iterations:
                iterations += 1
                messages = self.memory.get_messages()

                response = await self.config.provider.complete(
                    messages=messages,
                    tools=tool_schemas or None,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )

                # --- Tool calls requested ----------------------------------
                if response.tool_calls:
                    if response.content:
                        self.memory.add("assistant", response.content)

                    tool_results: list[str] = []
                    for tc in response.tool_calls:
                        all_tool_calls.append(
                            {"name": tc.name, "arguments": tc.arguments}
                        )
                        self._log.debug("Calling tool %s with %s", tc.name, tc.arguments)
                        tool = self._tool_map.get(tc.name)
                        if tool:
                            result: ToolResult = await tool.execute(**tc.arguments)
                            output = redact_secrets(result.to_string())
                            tool_results.append(
                                f"[Tool: {tc.name}] {'OK' if result.success else 'ERROR'}: {output}"
                            )
                        else:
                            tool_results.append(
                                f"[Tool: {tc.name}] ERROR: Tool not available to this agent."
                            )

                    self.memory.add("user", "Tool results:\n" + "\n".join(tool_results))
                    continue  # loop back for LLM to process results

                # --- Final answer -----------------------------------------
                final = redact_secrets(response.content)
                self.memory.add("assistant", final)

                if stream_callback:
                    stream_callback(final)

                return AgentResult(
                    agent_id=self.id,
                    agent_name=self.name,
                    content=final,
                    tool_calls=all_tool_calls,
                    iterations=iterations,
                    success=True,
                )

            # Max iterations reached without a text-only response
            return AgentResult(
                agent_id=self.id,
                agent_name=self.name,
                content="Max iterations reached. Last partial output may be incomplete.",
                tool_calls=all_tool_calls,
                iterations=iterations,
                success=False,
                error="max_iterations_exceeded",
            )

        except Exception as exc:
            self._log.error("Agent %s error: %s", self.id, exc, exc_info=True)
            return AgentResult(
                agent_id=self.id,
                agent_name=self.name,
                content="",
                iterations=iterations,
                success=False,
                error=str(exc),
            )

    async def stream(self, user_message: str) -> AsyncIterator[str]:
        """Stream tokens without tool use (pure generation mode)."""
        self.memory.add("user", user_message)
        full = ""
        async for token in self.config.provider.stream(
            messages=self.memory.get_messages(),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        ):
            clean = redact_secrets(token)
            full += clean
            yield clean
        self.memory.add("assistant", full)

    # ------------------------------------------------------------------
    # Memory control
    # ------------------------------------------------------------------

    def reset_memory(self) -> None:
        self.memory.clear()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_info(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.config.description,
            "provider": self.config.provider.get_info(),
            "tools": list(self._tool_map.keys()),
            "privilege_level": self.config.privilege_level,
            "tags": self.config.tags,
            "system_prompt_preview": self.config.system_prompt[:120],
        }
