"""
Conversation memory — keeps a sliding window of messages per agent session.
"""
from collections import deque
from typing import Optional

from .providers.base import Message


class ConversationMemory:
    """
    Manages a conversation history for a single agent.
    Older messages are automatically evicted when max_messages is reached.
    """

    def __init__(
        self,
        max_messages: int = 50,
        system_prompt: Optional[str] = None,
    ):
        self.max_messages = max_messages
        self.system_prompt = system_prompt
        self._messages: deque[Message] = deque(maxlen=max_messages)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------
    def add(self, role: str, content: str) -> None:
        self._messages.append(Message(role=role, content=content))

    def clear(self) -> None:
        self._messages.clear()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------
    def get_messages(self, include_system: bool = True) -> list[Message]:
        """Return the full message list ready to send to an LLM provider."""
        result: list[Message] = []
        if include_system and self.system_prompt:
            result.append(Message(role="system", content=self.system_prompt))
        result.extend(self._messages)
        return result

    def to_dict_list(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def __len__(self) -> int:
        return len(self._messages)

    def __repr__(self) -> str:
        return f"ConversationMemory(messages={len(self._messages)}, max={self.max_messages})"
