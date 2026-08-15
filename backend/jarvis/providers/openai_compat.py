"""Providers backed by any OpenAI-compatible REST endpoint."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from ..config import Settings
from ..tools import ToolBox
from .base import ChatMessage, ProviderError, ToolCall, ToolCallFunction, ToolChatMessage


class OpenAICompatLLM:
    name = "openai-compatible"

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def stream(
        self, messages: Sequence[ChatMessage], tools: ToolBox | None = None
    ) -> AsyncIterator[str]:
        """Stream a reply, running any tools the model asks for before it answers."""
        turn: list[ChatMessage] = list(messages)
        rounds = max(1, self._settings.max_tool_rounds)
        for _ in range(rounds):
            content = ""
            calls: list[ToolCall] = []
            async for event in self._round(turn, tools):
                if isinstance(event, str):
                    content += event
                    yield event
                else:
                    calls = event
            if not calls or tools is None:
                return
            turn.append(_assistant_call(content, calls))
            for call in calls:
                function = call["function"]
                result = await tools.invoke_json(function["name"], function["arguments"])
                reply: ToolChatMessage = {
                    "role": "tool",
                    "content": result,
                    "tool_call_id": call["id"],
                }
                turn.append(reply)

    async def _round(
        self, messages: Sequence[ChatMessage], tools: ToolBox | None
    ) -> AsyncIterator[str | list[ToolCall]]:
        """Yield content fragments, then finally the tool calls the model requested."""
        payload: dict[str, object] = {
            "model": self._settings.chat_model,
            "messages": list(messages),
            "stream": True,
            "temperature": 0.6,
        }
        if tools is not None and len(tools):
            payload["tools"] = tools.specs()
            payload["tool_choice"] = "auto"
        pending: dict[int, ToolCall] = {}
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
                    delta = _delta_of(data)
                    if delta is None:
                        continue
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
                    _merge_tool_calls(pending, delta.get("tool_calls"))
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ProviderError(f"chat completion transport error: {exc}") from exc
        yield [pending[index] for index in sorted(pending)]


def _delta_of(data: str) -> dict[str, object] | None:
    try:
        chunk = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(chunk, dict):
        return None
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    delta = first.get("delta") if isinstance(first, dict) else None
    return delta if isinstance(delta, dict) else None


def _merge_tool_calls(pending: dict[int, ToolCall], raw: object) -> None:
    """Streamed tool calls arrive as fragments keyed by index; stitch them together."""
    if not isinstance(raw, list):
        return
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        index = entry.get("index")
        index = int(index) if isinstance(index, int) else len(pending)
        call = pending.setdefault(
            index,
            ToolCall(
                id=f"call_{index}",
                type="function",
                function=ToolCallFunction(name="", arguments=""),
            ),
        )
        identifier = entry.get("id")
        if isinstance(identifier, str) and identifier:
            call["id"] = identifier
        function = entry.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if isinstance(name, str) and name:
            call["function"]["name"] += name
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            call["function"]["arguments"] += arguments


def _assistant_call(content: str, calls: list[ToolCall]) -> ToolChatMessage:
    return {"role": "assistant", "content": content, "tool_calls": calls}


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
