"""
Code execution tools — Python sandbox and shell commands.
WARNING: These tools execute arbitrary code. Only enable for trusted agents.
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .base import BaseTool, ToolResult


class ExecutePythonTool(BaseTool):
    name = "execute_python"
    description = (
        "Execute a Python code snippet and return stdout/stderr. "
        "Use this to perform calculations, data processing, or file operations."
    )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["code"],
        }

    async def execute(self, code: str, timeout: int = 30) -> ToolResult:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        try:
            tmp.write(code)
            tmp.close()

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                tmp.name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False, output=None, error=f"Timed out after {timeout}s"
                )

            out = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")

            if proc.returncode == 0:
                return ToolResult(success=True, output=out or "(no output)")
            return ToolResult(success=False, output=out, error=err)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


class ExecuteShellTool(BaseTool):
    name = "execute_shell"
    description = "Execute a shell command and return its stdout/stderr/exit-code."

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command"},
                "working_dir": {"type": "string", "description": "Working directory"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        }

    async def execute(
        self, command: str, working_dir: Optional[str] = None, timeout: int = 30
    ) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return ToolResult(
                    success=False, output=None, error=f"Command timed out after {timeout}s"
                )

            return ToolResult(
                success=proc.returncode == 0,
                output={
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "returncode": proc.returncode,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))
