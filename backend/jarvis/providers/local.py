"""Offline providers so Jarvis boots and answers without any API key."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from ..skills import answer_locally
from .base import ChatMessage


class LocalLLM:
    """Rule-based fallback brain.

    It handles the built-in skills (clock, arithmetic, small talk) and otherwise
    explains how to plug a real model in.
    """

    name = "local-rules"

    def __init__(self, chunk_delay: float = 0.012) -> None:
        self._chunk_delay = chunk_delay

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        prompt = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "",
        )
        reply = answer_locally(prompt)
        for word in reply.split(" "):
            yield word + " "
            if self._chunk_delay:
                await asyncio.sleep(self._chunk_delay)


class UnavailableSTT:
    """Placeholder telling the client to transcribe in the browser instead."""

    name = "browser"
    available = False

    async def transcribe(self, audio: bytes, mime: str) -> str:
        raise NotImplementedError("server-side transcription is disabled")


class UnavailableTTS:
    """Placeholder telling the client to use the Web Speech synthesizer."""

    name = "browser"
    available = False
    mime = "audio/mpeg"

    async def synthesize(self, text: str) -> bytes:
        raise NotImplementedError("server-side speech synthesis is disabled")
