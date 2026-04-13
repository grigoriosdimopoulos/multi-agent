"""
Anthropic Provider — Claude family of models.
"""
from typing import AsyncIterator, Optional

import anthropic as anthropic_sdk

from .base import BaseLLMProvider, CompletionResponse, Message, ToolCall


class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model=model, api_key=api_key, **kwargs)
        self._client = anthropic_sdk.AsyncAnthropic(api_key=api_key)

    def _split_messages(self, messages: list[Message]) -> tuple[str, list[dict]]:
        """Separate system prompt from conversation messages."""
        system = ""
        msgs: list[dict] = []
        for m in messages:
            if m.role == "system":
                system += ("\n" if system else "") + m.content
            else:
                msgs.append({"role": m.role, "content": m.content})
        return system, msgs

    async def complete(
        self,
        messages: list[Message],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> CompletionResponse:
        system, msgs = self._split_messages(messages)
        extra: dict = {}
        if system:
            extra["system"] = system
        if tools:
            anthropic_tools = []
            for t in tools:
                if t.get("type") == "function":
                    fn = t["function"]
                    anthropic_tools.append(
                        {
                            "name": fn["name"],
                            "description": fn.get("description", ""),
                            "input_schema": fn.get("parameters", {}),
                        }
                    )
            if anthropic_tools:
                extra["tools"] = anthropic_tools

        response = await self._client.messages.create(
            model=self.model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        )

        text_content = ""
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )

        return CompletionResponse(
            content=text_content,
            model=self.model,
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
            },
            finish_reason=response.stop_reason or "stop",
        )

    async def stream(
        self,
        messages: list[Message],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        system, msgs = self._split_messages(messages)
        extra: dict = {}
        if system:
            extra["system"] = system

        async with self._client.messages.stream(
            model=self.model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra,
        ) as stream:
            async for text in stream.text_stream:
                yield text
