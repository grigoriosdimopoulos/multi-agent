"""
Tool Registry — central catalog of all available tools.

Agents declare which tools they need by name; the registry hands back
the configured instances. New tools can be registered at runtime.
"""
from typing import Optional

from .base import BaseTool
from .file_tools import ListDirectoryTool, ReadFileTool, SearchInFilesTool, WriteFileTool
from .web_tools import FetchWebPageTool, HTTPRequestTool
from .code_tools import ExecutePythonTool, ExecuteShellTool


class ToolRegistry:
    """Singleton-style catalog of BaseTool instances."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._register_defaults()

    # ------------------------------------------------------------------
    # Defaults
    # ------------------------------------------------------------------
    def _register_defaults(self) -> None:
        for tool in [
            ReadFileTool(),
            WriteFileTool(),
            ListDirectoryTool(),
            SearchInFilesTool(),
            FetchWebPageTool(),
            HTTPRequestTool(),
            ExecutePythonTool(),
            ExecuteShellTool(),
        ]:
            self.register(tool)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_many(self, names: list[str]) -> list[BaseTool]:
        return [self._tools[n] for n in names if n in self._tools]

    def get_all(self) -> list[BaseTool]:
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self, names: Optional[list[str]] = None) -> list[dict]:
        tools = self.get_many(names) if names else self.get_all()
        return [t.schema for t in tools]

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------
    def describe(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={self.list_names()})"


# Module-level singleton — shared across the process unless overridden.
tool_registry = ToolRegistry()
