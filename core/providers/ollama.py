"""
Ollama Provider — default is free, local inference (no API key).

Typical setup: OLLAMA_HOST=http://localhost:11434, OLLAMA unset/empty.
Install: https://ollama.com — run `ollama serve`, then `ollama pull <model>`.

Optional: OLLAMA_API_KEY is only for ollama.com’s hosted API, not local :11434.
"""
import json
import os
from typing import AsyncIterator, Optional

import httpx

from .base import BaseLLMProvider, CompletionResponse, Message, ToolCall


class OllamaProvider(BaseLLMProvider):
    """Local or cloud Ollama HTTP API (Bearer auth when OLLAMA_API_KEY is set)."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        api_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model=model, api_key=api_key, base_url=base_url, **kwargs)
        # Reuse one client so we keep a warm HTTP connection to Ollama (faster TTFT).
        self._http: httpx.AsyncClient | None = None
        _key = (api_key or os.getenv("OLLAMA_API_KEY") or "").strip()
        self._auth_headers: dict[str, str] = {}
        if _key:
            self._auth_headers["Authorization"] = f"Bearer {_key}"

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=15.0),
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                headers=self._auth_headers or None,
            )
        return self._http

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_ollama_messages(messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    async def complete(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> CompletionResponse:
        payload: dict = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        client = self._ensure_http()
        resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        msg = data.get("message", {})
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_calls.append(ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args))

        return CompletionResponse(
            content=msg.get("content", ""),
            model=self.model,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": self._to_ollama_messages(messages),
            "stream": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        client = self._ensure_http()
        async with client.stream(
            "POST", f"{self.base_url}/api/chat", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if content := chunk.get("message", {}).get("content", ""):
                        yield content
                    if chunk.get("done"):
                        break

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Ollama (requires a model that supports it)."""
        embeddings: list[list[float]] = []
        client = self._ensure_http()
        for text in texts:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        return embeddings

    async def list_models(self) -> list[str]:
        """Return all locally available Ollama models."""
        client = self._ensure_http()
        resp = await client.get(f"{self.base_url}/api/tags")
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
