"""Provider protocols. Every backend capability is swappable."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, TypedDict, runtime_checkable

from ..tools import ToolBox


class ToolCallFunction(TypedDict):
    name: str
    arguments: str


class ToolCall(TypedDict):
    id: str
    type: str
    function: ToolCallFunction


class ChatMessage(TypedDict):
    role: str
    content: str


class ToolChatMessage(ChatMessage, total=False):
    """A turn that requested tools, or the result handed back to the model."""

    tool_calls: list[ToolCall]
    tool_call_id: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def stream(
        self, messages: Sequence[ChatMessage], tools: ToolBox | None = None
    ) -> AsyncIterator[str]:
        """Yield reply fragments as they are produced, calling ``tools`` when asked."""


@runtime_checkable
class STTProvider(Protocol):
    name: str
    available: bool

    async def transcribe(self, audio: bytes, mime: str) -> str:
        """Return the text of a complete spoken utterance."""


@runtime_checkable
class TTSProvider(Protocol):
    name: str
    available: bool
    mime: str

    async def synthesize(self, text: str) -> bytes:
        """Return encoded audio for ``text``."""


class ProviderError(RuntimeError):
    """Raised when an upstream provider fails in a recoverable way."""
