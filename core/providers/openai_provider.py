"""
OpenAI Provider — works with the official API and any OpenAI-compatible endpoint
(OpenRouter, LM Studio, vLLM, etc.) by setting base_url.
"""
import json
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from .base import BaseLLMProvider, CompletionResponse, Message, ToolCall


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model=model, api_key=api_key, base_url=base_url, **kwargs)
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def _to_oai_messages(messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def complete(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> CompletionResponse:
        extra: dict = {}
        if tools:
            extra["tools"] = tools
            extra["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=self._to_oai_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )

        choice = response.choices[0]
        tool_calls: list[ToolCall] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return CompletionResponse(
            content=choice.message.content or "",
            model=self.model,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            },
            finish_reason=choice.finish_reason or "stop",
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self.model,
            messages=self._to_oai_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in response.data]
