"""
Security module — API key auth, path sandboxing, rate limiting.

Design principles:
  - No secrets in code  → keys come exclusively from environment / .env
  - Least privilege     → agents declare the tools they need; others blocked
  - Path sandboxing     → file tools restricted to ALLOWED_BASE_DIRS
  - Rate limiting       → per-IP token-bucket to protect the master API
  - Secret scanning     → strip common secret patterns from LLM output
"""
import hashlib
import hmac
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional


# -----------------------------------------------------------------------
# API Key Auth
# -----------------------------------------------------------------------

def _load_api_keys() -> set[str]:
    """Load allowed API keys from the MASTER_API_KEYS env var (comma-separated)."""
    raw = os.getenv("MASTER_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def master_api_key_auth_enabled() -> bool:
    """True when at least one non-empty key is configured (not merely a non-empty env string)."""
    return bool(_load_api_keys())


def verify_api_key(key: str) -> bool:
    """Constant-time comparison against all registered API keys."""
    allowed = _load_api_keys()
    if not allowed:
        # No keys configured → open access (dev mode).
        return True
    return any(hmac.compare_digest(key, k) for k in allowed)


def verify_node_secret(secret: str) -> bool:
    """Verify a node's shared secret (NODE_SHARED_SECRET env var)."""
    expected = os.getenv("NODE_SHARED_SECRET", "")
    if not expected:
        return True  # dev mode
    return hmac.compare_digest(secret, expected)


# -----------------------------------------------------------------------
# Path Sandboxing
# -----------------------------------------------------------------------

class PathSandbox:
    """
    Restrict file operations to one or more allowed base directories.

    Usage:
        sandbox = PathSandbox(["/data/workspace", "/tmp/agents"])
        safe_path = sandbox.resolve("/data/workspace/report.txt")  # OK
        sandbox.resolve("/etc/passwd")  # raises PermissionError
    """

    def __init__(self, allowed_dirs: Optional[list[str]] = None):
        env_dirs = os.getenv("ALLOWED_DIRS", "")
        default_dirs = [d.strip() for d in env_dirs.split(":") if d.strip()]
        dirs = allowed_dirs or default_dirs or [str(Path.cwd() / "workspace")]
        self._allowed = [Path(d).resolve() for d in dirs]

    def resolve(self, path: str) -> Path:
        """Return *path* resolved to an absolute Path, or raise PermissionError."""
        resolved = Path(path).resolve()
        if not any(
            resolved == base or base in resolved.parents
            for base in self._allowed
        ):
            raise PermissionError(
                f"Access denied: '{path}' is outside the allowed directories: "
                + ", ".join(str(d) for d in self._allowed)
            )
        return resolved

    def is_allowed(self, path: str) -> bool:
        try:
            self.resolve(path)
            return True
        except PermissionError:
            return False

    def add_allowed_dir(self, directory: str) -> None:
        self._allowed.append(Path(directory).resolve())


# -----------------------------------------------------------------------
# Rate Limiting
# -----------------------------------------------------------------------

class RateLimiter:
    """
    Simple token-bucket rate limiter keyed by client identifier (IP, API key…).

    Default: 60 requests / minute per identity.
    """

    def __init__(self, max_requests: int = 60, window_seconds: float = 60.0):
        self._max = max_requests
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, identity: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        bucket = self._buckets[identity]
        # Evict timestamps outside the window
        self._buckets[identity] = [t for t in bucket if t > cutoff]
        if len(self._buckets[identity]) >= self._max:
            return False
        self._buckets[identity].append(now)
        return True

    def remaining(self, identity: str) -> int:
        now = time.monotonic()
        cutoff = now - self._window
        count = sum(1 for t in self._buckets.get(identity, []) if t > cutoff)
        return max(0, self._max - count)


# -----------------------------------------------------------------------
# Secret Scanner  (strip accidental leaks from LLM output)
# -----------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(r'(?i)(api[_-]?key|secret|password|token|bearer)\s*[=:]\s*\S+'),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),           # OpenAI keys
    re.compile(r'ghp_[A-Za-z0-9]{36}'),            # GitHub PAT
    re.compile(r'AKIA[0-9A-Z]{16}'),               # AWS access key
    re.compile(r'-----BEGIN (RSA |EC )?PRIVATE KEY-----'),
]


def scan_for_secrets(text: str) -> list[str]:
    """Return a list of detected secret patterns found in *text*."""
    found: list[str] = []
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            found.append(pattern.pattern)
    return found


def redact_secrets(text: str) -> str:
    """Replace detected secrets with [REDACTED]."""
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


# -----------------------------------------------------------------------
# Privilege Levels
# -----------------------------------------------------------------------

class PrivilegeLevel:
    """
    Declare what a given agent role is permitted to do.

    Levels (additive):
        READ_ONLY  – read files, query knowledge, fetch web pages
        STANDARD   – + write files, HTTP requests
        ELEVATED   – + execute Python/shell code
        ADMIN      – + manage agents, nodes, knowledge collections
    """
    READ_ONLY = 0
    STANDARD  = 1
    ELEVATED  = 2
    ADMIN     = 3

    # Tool-name sets per level
    ALLOWED_TOOLS: dict[int, set[str]] = {
        READ_ONLY: {"read_file", "list_directory", "search_in_files",
                    "fetch_webpage", "query_knowledge_base",
                    "read_excel", "read_word", "read_pdf", "read_csv"},
        STANDARD:  {"write_file", "http_request", "write_excel",
                    "write_word", "write_csv"},
        ELEVATED:  {"execute_python", "execute_shell"},
        ADMIN:     {"__all__"},
    }

    @classmethod
    def permitted_tools(cls, level: int) -> set[str]:
        tools: set[str] = set()
        for lvl in sorted(cls.ALLOWED_TOOLS):
            if lvl <= level:
                tools |= cls.ALLOWED_TOOLS[lvl]
        return tools

    @classmethod
    def can_use_tool(cls, level: int, tool_name: str) -> bool:
        allowed = cls.permitted_tools(level)
        return "__all__" in allowed or tool_name in allowed


# Module-level singletons
rate_limiter = RateLimiter(
    max_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "60")),
    window_seconds=float(os.getenv("RATE_LIMIT_WINDOW", "60")),
)
path_sandbox = PathSandbox()
