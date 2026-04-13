"""
Ollama-based embedding function for ChromaDB.

Uses the locally running Ollama server for embeddings, which supports
multilingual text (Greek, English, etc.) and avoids the broken ONNX
default on macOS ARM.
"""
import os
from typing import Optional

import httpx
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    """Generate embeddings via Ollama's /api/embed endpoint."""

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: Optional[str] = None,
    ):
        self._model = model
        self._base_url = (
            base_url
            or os.getenv("OLLAMA_HOST")
            or "http://localhost:11434"
        ).rstrip("/")

    def __call__(self, input: Documents) -> Embeddings:
        if not input:
            return []
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": input},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"]
