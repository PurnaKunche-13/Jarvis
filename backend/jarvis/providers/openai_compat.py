"""Providers backed by any OpenAI-compatible REST endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from ..config import Settings
from .base import ChatMessage, ProviderError


class OpenAICompatLLM:
    name = "openai-compatible"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        payload = {
            "model": self._settings.chat_model,
            "messages": list(messages),
            "stream": True,
            "temperature": 0.6,
        }
        try:
            async with self._client.stream(
                "POST", "/chat/completions", json=payload
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread()).decode("utf-8", "replace")[:400]
                    raise ProviderError(
                        f"chat completion failed ({response.status_code}): {detail}"
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    fragment = _delta_of(data)
                    if fragment:
                        yield fragment
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"chat completion transport error: {exc}") from exc


def _delta_of(data: str) -> str:
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return ""
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else ""


class OpenAICompatSTT:
    name = "openai-compatible"
    available = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def transcribe(self, audio: bytes, mime: str) -> str:
        suffix = _extension_for(mime)
        files = {"file": (f"utterance.{suffix}", audio, mime)}
        data = {"model": self._settings.stt_model, "response_format": "json"}
        try:
            response = await self._client.post("/audio/transcriptions", data=data, files=files)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"transcription transport error: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"transcription failed ({response.status_code}): {response.text[:400]}"
            )
        return str(response.json().get("text", "")).strip()


class OpenAICompatTTS:
    name = "openai-compatible"
    available = True
    mime = "audio/mpeg"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def synthesize(self, text: str) -> bytes:
        payload = {
            "model": self._settings.tts_model,
            "voice": self._settings.tts_voice,
            "input": text,
            "response_format": "mp3",
        }
        try:
            response = await self._client.post("/audio/speech", json=payload)
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"speech transport error: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(f"speech failed ({response.status_code}): {response.text[:400]}")
        return response.content


_EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


def _extension_for(mime: str) -> str:
    return _EXTENSIONS.get(mime.split(";")[0].strip().lower(), "webm")
