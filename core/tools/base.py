"""
Base classes for the tool system.

Tools are the "hands" of an agent — they let it interact with the world.
Each tool exposes:
  - name        unique identifier used by the LLM
  - description human-readable purpose (shown to LLM)
  - schema      OpenAI-compatible JSON schema for the parameters
  - execute()   async call that performs the action and returns a ToolResult
"""
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ToolResult:
    """Outcome of a single tool execution."""
    success: bool
    output: Any
    error: Optional[str] = None

    def to_string(self) -> str:
        if self.success:
            if isinstance(self.output, str):
                return self.output
            return json.dumps(self.output, ensure_ascii=False, default=str)
        return f"Error: {self.error}"


class BaseTool(ABC):
    """Abstract base for every tool in the system."""

    name: str = ""
    description: str = ""

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    @property
    def schema(self) -> dict:
        """OpenAI-compatible function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """JSON Schema describing the tool\'s parameters."""
        ...

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Run the tool and return a ToolResult."""
        ...

    def __repr__(self) -> str:
        return f"Tool(name={self.name!r})"
