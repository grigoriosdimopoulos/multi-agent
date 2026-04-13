"""
Groq Provider — ultra-fast inference via Groq Cloud (free tier available).
https://console.groq.com
"""
import json
from typing import AsyncIterator, Optional

from groq import AsyncGroq

from .base import BaseLLMProvider, CompletionResponse, Message, ToolCall


class GroqProvider(BaseLLMProvider):
    provider_name = "groq"

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model=model, api_key=api_key, **kwargs)
        self._client = AsyncGroq(api_key=api_key)

    @staticmethod
    def _to_groq_messages(messages: list[Message]) -> list[dict]:
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
            messages=self._to_groq_messages(messages),
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
            messages=self._to_groq_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
