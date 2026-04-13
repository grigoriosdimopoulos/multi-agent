from typing import Optional
from .base import BaseLLMProvider, Message, CompletionResponse, ToolCall
from .ollama import OllamaProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .groq_provider import GroqProvider

PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "groq": GroqProvider,
}


def create_provider(provider_type: str, **kwargs) -> BaseLLMProvider:
    """Factory function to create an LLM provider instance."""
    cls = PROVIDERS.get(provider_type)
    if not cls:
        raise ValueError(
            f"Unknown provider: '{provider_type}'. "
            f"Available providers: {list(PROVIDERS.keys())}"
        )
    return cls(**kwargs)


__all__ = [
    "BaseLLMProvider",
    "Message",
    "CompletionResponse",
    "ToolCall",
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GroqProvider",
    "create_provider",
    "PROVIDERS",
]
