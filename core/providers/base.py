from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class Message:
    """Represents a single message in a conversation."""
    role: str   # "user" | "assistant" | "system" | "tool"
    content: str
    name: Optional[str] = None


@dataclass
class ToolCall:
    """Represents a tool invocation requested by the LLM."""
    id: str
    name: str
    arguments: dict


@dataclass
class CompletionResponse:
    """Represents the LLM completion result."""
    content: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = "stop"


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Each provider (Ollama, OpenAI, Anthropic, Groq …) must implement:
        - complete()  – single-shot completion
        - stream()    – token-by-token streaming
        - embed()     – optional text embeddings
    """

    provider_name: str = "base"

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.config = kwargs

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> CompletionResponse:
        """Generate a single completion from a list of messages."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Yield response tokens one by one."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts (provider must support it)."""
        raise NotImplementedError(
            f"Embedding is not supported by provider '{self.provider_name}'"
        )

    def get_info(self) -> dict:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "base_url": self.base_url,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r})"
