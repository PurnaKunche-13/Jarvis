from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx
import pytest

from jarvis.config import Settings
from jarvis.tools import ToolBox, build_toolbox, match_intent
from jarvis.tools.base import ToolError
from jarvis.tools.search import WebSearchTool, parse_brave, parse_duckduckgo
from jarvis.tools.system import SystemInfoTool
from jarvis.tools.timers import (
    MAX_SECONDS,
    CancelTimerTool,
    ListTimersTool,
    SetTimerTool,
    TimerService,
    humanize,
    parse_duration,
)

DUCK_HTML = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnasa.gov%2Fmars"
     >Mars &amp; you</a>
  <a class="result__snippet">The <b>fourth</b> planet.</a>
</div>
<div class="result">
  <a class="result__a" href="https://esa.int/mars">ESA Mars</a>
  <a class="result__snippet">European mission.</a>
</div>
"""


def notices() -> tuple[list[str], object]:
    sink: list[str] = []

    async def notify(text: str) -> None:
        sink.append(text)

    return sink, notify


async def test_timer_fires_and_announces_itself() -> None:
    sink, notify = notices()
    service = TimerService(notify)  # type: ignore[arg-type]
    tool = SetTimerTool(service)

    assert "set for" in await tool.run({"seconds": 0.01, "label": "tea"})
    await asyncio.sleep(0.05)

    assert sink == ["Your tea is up."]
    assert service.active == []


async def test_timers_can_be_listed_and_cancelled() -> None:
    _, notify = notices()
    service = TimerService(notify)  # type: ignore[arg-type]
    await SetTimerTool(service).run({"minutes": 5, "label": "pasta"})
    await SetTimerTool(service).run({"minutes": 9})

    listed = await ListTimersTool(service).run({})
    assert "pasta" in listed and "5 minutes" in listed

    assert "Cancelled timer 1" in await CancelTimerTool(service).run({"id": 1})
    assert "Cancelled timer 2" in await CancelTimerTool(service).run({})
    assert service.active == []
    await service.aclose()


async def test_timer_limits_are_enforced() -> None:
    _, notify = notices()
    service = TimerService(notify)  # type: ignore[arg-type]

    with pytest.raises(ToolError):
        service.start(MAX_SECONDS + 1, "forever")
    with pytest.raises(ToolError):
        service.start(0, "instant")
    with pytest.raises(ToolError):
        await SetTimerTool(service).run({"label": "vague"})


async def test_closing_a_session_drops_pending_timers() -> None:
    sink, notify = notices()
    service = TimerService(notify)  # type: ignore[arg-type]
    service.start(0.01, "tea")

    await service.aclose()
    await asyncio.sleep(0.05)

    assert sink == []


def test_humanize_and_duration_parsing() -> None:
    assert humanize(45) == "45 seconds"
    assert humanize(90) == "1 minute 30 seconds"
    assert humanize(7200) == "2 hours"

    assert parse_duration("set a timer for 10 minutes") == (600.0, "timer")
    assert parse_duration("start a tea timer for 3 min") == (180.0, "tea timer")
    assert parse_duration("remind me to stretch in 30 seconds") == (30.0, "stretch")
    assert parse_duration("set a timer") is None


def test_intents_route_spoken_commands_to_tools() -> None:
    assert match_intent("set a timer for 2 minutes") == (
        "set_timer",
        {"seconds": 120.0, "label": "timer"},
    )
    assert match_intent("what timers are running?") == ("list_timers", {})
    assert match_intent("cancel timer 2") == ("cancel_timer", {"id": 2})
    assert match_intent("stop all timers") == ("cancel_timer", {})
    assert match_intent("system status") == ("system_info", {})
    assert match_intent("search the web for mars rovers") == (
        "web_search",
        {"query": "mars rovers", "limit": 3},
    )
    assert match_intent("tell me a story") is None


async def test_toolbox_reports_unknown_and_malformed_calls() -> None:
    box, timers = build_toolbox(Settings(), httpx.AsyncClient(), _ignore)

    assert box.names == [
        "cancel_timer",
        "list_timers",
        "set_timer",
        "system_info",
        "web_search",
    ]
    names = {
        spec["function"]["name"]  # type: ignore[index]
        for spec in box.specs()
    }
    assert names == set(box.names)
    assert await box.invoke_json("nope", "{}") == "Unknown tool: nope"
    assert await box.invoke_json("set_timer", "{oops") == "Malformed arguments for set_timer."
    assert await box.invoke_json("set_timer", "[]") == "Arguments for set_timer must be an object."
    assert "how long" in await box.invoke("set_timer", {})
    await timers.aclose()


async def test_system_info_reports_the_host_without_secrets() -> None:
    report = await SystemInfoTool().run({})

    assert "CPUs" in report
    assert "JARVIS" not in report and "KEY" not in report


def test_duckduckgo_results_are_unwrapped_and_cleaned() -> None:
    results = parse_duckduckgo(DUCK_HTML, limit=5)

    assert [result.url for result in results] == ["https://nasa.gov/mars", "https://esa.int/mars"]
    assert results[0].title == "Mars & you"
    assert results[0].snippet == "The fourth planet."
    assert len(parse_duckduckgo(DUCK_HTML, limit=1)) == 1


def test_brave_payload_is_parsed() -> None:
    payload: Mapping[str, object] = {
        "web": {
            "results": [
                {"title": "Mars", "url": "https://nasa.gov", "description": "Red <b>planet</b>"},
                {"title": "", "url": "https://skip.me"},
            ]
        }
    }
    results = parse_brave(payload, limit=5)

    assert len(results) == 1
    assert results[0].snippet == "Red planet"
    assert parse_brave({}, limit=5) == []


async def test_web_search_uses_duckduckgo_without_a_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=DUCK_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = WebSearchTool(Settings(), client)

    result = await tool.run({"query": "mars", "limit": 2})

    assert seen[0].url.host == "html.duckduckgo.com"
    assert result.startswith("1. Mars & you")
    assert "2. ESA Mars" in result


async def test_web_search_uses_brave_when_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-subscription-token"] == "brave-key"
        return httpx.Response(200, json={"web": {"results": [{"title": "M", "url": "https://m"}]}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = WebSearchTool(Settings(search_api_key="brave-key"), client)

    assert "https://m" in await tool.run({"query": "mars"})


async def test_web_search_failures_become_spoken_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="busy")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    box = ToolBox([WebSearchTool(Settings(), client)])

    assert await box.invoke("web_search", {"query": "mars"}) == "Search failed (503)."
    assert "Missing required argument" in await box.invoke("web_search", {})


async def _ignore(_: str) -> None:
    """Notifier that drops notices."""
