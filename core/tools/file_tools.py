"""
File system tools — read, write, list, and search files.
"""
from pathlib import Path
from typing import Optional

from .base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Optionally specify start/end line numbers."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"},
                "start_line": {"type": "integer", "description": "1-indexed start line (optional)"},
                "end_line": {"type": "integer", "description": "1-indexed end line (optional)"},
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(success=False, output=None, error=f"File not found: {path}")
            content = p.read_text(encoding="utf-8", errors="replace")
            if start_line or end_line:
                lines = content.splitlines()
                start = (start_line or 1) - 1
                end = end_line or len(lines)
                content = "\n".join(lines[start:end])
            return ToolResult(success=True, output=content)
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write text content to a file (creates parent directories as needed)."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Destination file path"},
                "content": {"type": "string", "description": "Text to write"},
                "append": {
                    "type": "boolean",
                    "description": "Append to existing file instead of overwriting",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str, append: bool = False) -> ToolResult:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with p.open(mode, encoding="utf-8") as fh:
                fh.write(content)
            return ToolResult(success=True, output=f"Written {len(content)} chars to {path}")
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List files and directories at a given path, with optional glob filtering."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list"},
                "recursive": {
                    "type": "boolean",
                    "description": "Recurse into subdirectories",
                    "default": False,
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern filter, e.g. '*.py'",
                    "default": "*",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self, path: str, recursive: bool = False, pattern: str = "*"
    ) -> ToolResult:
        try:
            p = Path(path)
            if not p.exists():
                return ToolResult(success=False, output=None, error=f"Path not found: {path}")
            files = list(p.rglob(pattern) if recursive else p.glob(pattern))
            result = [
                {
                    "path": str(f.relative_to(p)),
                    "type": "dir" if f.is_dir() else "file",
                    "size": f.stat().st_size if f.is_file() else None,
                }
                for f in sorted(files)
            ]
            return ToolResult(success=True, output=result)
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class SearchInFilesTool(BaseTool):
    name = "search_in_files"
    description = "Search for a text pattern across files in a directory. Returns matching lines."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Text or regex pattern"},
                "file_pattern": {
                    "type": "string",
                    "description": "File glob to restrict search, e.g. '*.py'",
                    "default": "*",
                },
                "max_results": {"type": "integer", "default": 50},
            },
            "required": ["directory", "pattern"],
        }

    async def execute(
        self,
        directory: str,
        pattern: str,
        file_pattern: str = "*",
        max_results: int = 50,
    ) -> ToolResult:
        import re
        try:
            results: list[dict] = []
            for f in Path(directory).rglob(file_pattern):
                if f.is_file() and len(results) < max_results:
                    try:
                        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                            if re.search(pattern, line, re.IGNORECASE):
                                results.append({"file": str(f), "line": i, "content": line.strip()})
                                if len(results) >= max_results:
                                    break
                    except Exception:
                        pass
            return ToolResult(success=True, output=results)
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))
