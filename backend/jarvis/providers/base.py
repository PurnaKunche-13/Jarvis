"""Provider protocols. Every backend capability is swappable."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, TypedDict, runtime_checkable


class ChatMessage(TypedDict):
    role: str
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield reply fragments as they are produced."""


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
