from __future__ import annotations

import base64
from collections.abc import AsyncIterator, Sequence

import httpx

from jarvis.config import Settings
from jarvis.providers.base import ChatMessage
from jarvis.providers.local import LocalLLM, UnavailableSTT, UnavailableTTS
from jarvis.registry import Runtime
from jarvis.session import Session
from jarvis.tools import ToolBox


class ScriptedSTT:
    name = "scripted"
    available = True

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[int, str]] = []

    async def transcribe(self, audio: bytes, mime: str) -> str:
        self.calls.append((len(audio), mime))
        return self.text


class ScriptedTTS:
    name = "scripted"
    available = True
    mime = "audio/mpeg"

    async def synthesize(self, text: str) -> bytes:
        return b"\x00audio" + text.encode()


class ScriptedLLM:
    name = "scripted"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.seen: list[Sequence[ChatMessage]] = []

    async def stream(
        self, messages: Sequence[ChatMessage], tools: ToolBox | None = None
    ) -> AsyncIterator[str]:
        self.seen.append(list(messages))
        for part in self.reply.split(" "):
            yield part + " "


def make_runtime(**overrides: object) -> tuple[Runtime, list[dict]]:
    settings = Settings(history_turns=2)
    runtime = Runtime(
        settings=settings,
        llm=overrides.get("llm", LocalLLM(chunk_delay=0)),
        stt=overrides.get("stt", UnavailableSTT()),
        tts=overrides.get("tts", UnavailableTTS()),
        client=None,
        web_client=httpx.AsyncClient(),
    )
    return runtime, []


def collector(sink: list[dict]):
    async def emit(message: object) -> None:
        sink.append(message.model_dump())

    return emit


async def test_text_turn_streams_tokens_and_defers_speech_to_browser() -> None:
    runtime, sink = make_runtime(llm=ScriptedLLM("At your service"))
    session = Session(runtime, collector(sink))

    await session.handle_text("hello")

    types = [event["type"] for event in sink]
    assert types[0] == "state" and sink[0]["value"] == "thinking"
    assert "token" in types
    end = next(event for event in sink if event["type"] == "reply_end")
    assert end["text"] == "At your service"
    assert end["speak"] is True
    # The browser is speaking, so the server must not knock the state back to idle.
    assert sink[-1] == {"type": "state", "value": "speaking"}
    assert [m["role"] for m in session.history] == ["user", "assistant"]


async def test_server_tts_emits_audio_and_speaking_state() -> None:
    runtime, sink = make_runtime(llm=ScriptedLLM("online"), tts=ScriptedTTS())
    session = Session(runtime, collector(sink))

    await session.handle_text("are you there")

    end = next(event for event in sink if event["type"] == "reply_end")
    assert end["speak"] is False
    audio = next(event for event in sink if event["type"] == "audio")
    assert base64.b64decode(audio["audio"]).startswith(b"\x00audio")
    assert sink[-1]["type"] == "audio"


async def test_audio_turn_transcribes_then_answers() -> None:
    stt = ScriptedSTT("what is 2 plus 2")
    runtime, sink = make_runtime(stt=stt)
    session = Session(runtime, collector(sink))

    await session.handle_audio(base64.b64encode(b"opus-bytes").decode(), "audio/webm")

    assert stt.calls == [(10, "audio/webm")]
    transcript = next(event for event in sink if event["type"] == "transcript")
    assert transcript["text"] == "what is 2 plus 2"
    end = next(event for event in sink if event["type"] == "reply_end")
    assert end["text"] == "4"


async def test_audio_without_server_stt_reports_error() -> None:
    runtime, sink = make_runtime()
    session = Session(runtime, collector(sink))

    await session.handle_audio(base64.b64encode(b"bytes").decode(), "audio/webm")

    assert sink[0]["type"] == "error"


async def test_malformed_audio_is_rejected() -> None:
    runtime, sink = make_runtime(stt=ScriptedSTT("ignored"))
    session = Session(runtime, collector(sink))

    await session.handle_audio("not base64!!", "audio/webm")

    assert sink[0]["type"] == "error"


async def test_history_is_trimmed_to_configured_turns() -> None:
    runtime, sink = make_runtime(llm=ScriptedLLM("ack"))
    session = Session(runtime, collector(sink))

    for index in range(5):
        await session.handle_text(f"message {index}")

    assert len(session.history) == 4
    assert session.history[0]["content"] == "message 3"

    session.reset()
    assert session.history == []


async def test_local_brain_routes_a_timer_command_through_the_tools() -> None:
    runtime, sink = make_runtime()
    session = Session(runtime, collector(sink))

    await session.handle_text("set a tea timer for 30 minutes")

    end = next(event for event in sink if event["type"] == "reply_end")
    assert "tea timer" in end["text"] and "30 minutes" in end["text"]

    await session.handle_text("what timers are running")
    ends = [event for event in sink if event["type"] == "reply_end"]
    assert "tea timer" in ends[-1]["text"]

    await session.aclose()


async def test_a_fired_timer_notifies_the_client_and_asks_it_to_speak() -> None:
    runtime, sink = make_runtime()
    session = Session(runtime, collector(sink))

    await session.notify("Your tea timer is up.")

    notice = next(event for event in sink if event["type"] == "notice")
    assert notice == {
        "type": "notice",
        "text": "Your tea timer is up.",
        "kind": "timer",
        "speak": True,
    }
    assert sink[-1] == {"type": "state", "value": "speaking"}
