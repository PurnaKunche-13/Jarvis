"""Per-connection conversation state and the turn pipeline."""

from __future__ import annotations

import base64
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic import BaseModel

from .providers.base import ChatMessage, ProviderError
from .registry import Runtime
from .schemas import (
    ServerAudio,
    ServerError,
    ServerReplyEnd,
    ServerState,
    ServerToken,
    ServerTranscript,
)

logger = logging.getLogger(__name__)

Emit = Callable[[BaseModel], Awaitable[None]]

MAX_AUDIO_BYTES = 8 * 1024 * 1024


class Session:
    """One hologram client: history, transcription and reply streaming."""

    def __init__(self, runtime: Runtime, emit: Emit) -> None:
        self._runtime = runtime
        self._emit = emit
        self._history: list[ChatMessage] = []

    @property
    def history(self) -> list[ChatMessage]:
        return list(self._history)

    def reset(self) -> None:
        self._history.clear()

    async def handle_audio(self, audio_b64: str, mime: str) -> None:
        if not self._runtime.stt.available:
            await self._emit(
                ServerError(message="Server transcription is unavailable; speak via the browser.")
            )
            return
        try:
            audio = base64.b64decode(audio_b64, validate=True)
        except (ValueError, TypeError):
            await self._emit(ServerError(message="Malformed audio payload."))
            return
        if not audio:
            await self._emit(ServerState(value="idle"))
            return
        if len(audio) > MAX_AUDIO_BYTES:
            await self._emit(ServerError(message="Utterance too long."))
            return

        await self._emit(ServerState(value="thinking"))
        try:
            text = await self._runtime.stt.transcribe(audio, mime)
        except (ProviderError, NotImplementedError) as exc:
            logger.warning("transcription failed: %s", exc)
            await self._emit(ServerError(message="I could not transcribe that."))
            await self._emit(ServerState(value="idle"))
            return
        if not text:
            await self._emit(ServerState(value="idle"))
            return
        await self._emit(ServerTranscript(text=text))
        await self.handle_text(text)

    async def handle_text(self, text: str) -> None:
        prompt = text.strip()
        if not prompt:
            return
        self._append("user", prompt)
        await self._emit(ServerState(value="thinking"))

        chunks: list[str] = []
        try:
            async for chunk in self._stream_reply():
                chunks.append(chunk)
                await self._emit(ServerToken(text=chunk))
        except ProviderError as exc:
            logger.warning("llm failed: %s", exc)
            await self._emit(ServerError(message="My language core is unreachable."))
            await self._emit(ServerState(value="idle"))
            return

        reply = "".join(chunks).strip()
        if not reply:
            await self._emit(ServerState(value="idle"))
            return
        self._append("assistant", reply)

        audio = await self._speak(reply)
        await self._emit(ServerReplyEnd(text=reply, speak=audio is None))
        if audio is not None:
            await self._emit(ServerState(value="speaking"))
            await self._emit(audio)
        else:
            await self._emit(ServerState(value="idle"))

    async def _speak(self, reply: str) -> ServerAudio | None:
        if not self._runtime.tts.available:
            return None
        try:
            payload = await self._runtime.tts.synthesize(reply)
        except (ProviderError, NotImplementedError) as exc:
            logger.warning("speech synthesis failed: %s", exc)
            return None
        if not payload:
            return None
        return ServerAudio(
            audio=base64.b64encode(payload).decode("ascii"),
            mime=self._runtime.tts.mime,
        )

    def _stream_reply(self) -> AsyncIterator[str]:
        messages: list[ChatMessage] = [
            {"role": "system", "content": self._runtime.settings.system_prompt}
        ]
        messages.extend(self._history)
        return self._runtime.llm.stream(messages)

    def _append(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        limit = max(2, self._runtime.settings.history_turns * 2)
        if len(self._history) > limit:
            del self._history[: len(self._history) - limit]
