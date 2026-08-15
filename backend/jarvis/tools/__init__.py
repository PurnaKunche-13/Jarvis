"""Jarvis tools: the skills both the model and the offline brain can call."""

from __future__ import annotations

import httpx

from ..config import Settings
from .base import JsonSchema, Notifier, Tool, ToolBox, ToolError
from .intents import match_intent
from .search import WebSearchTool
from .system import SystemInfoTool
from .timers import CancelTimerTool, ListTimersTool, SetTimerTool, TimerService

__all__ = [
    "CancelTimerTool",
    "JsonSchema",
    "ListTimersTool",
    "Notifier",
    "SetTimerTool",
    "SystemInfoTool",
    "TimerService",
    "Tool",
    "ToolBox",
    "ToolError",
    "WebSearchTool",
    "build_toolbox",
    "match_intent",
]


def build_toolbox(
    settings: Settings, web_client: httpx.AsyncClient, notify: Notifier
) -> tuple[ToolBox, TimerService]:
    """Assemble one session's tools; the timer service is returned so it can be closed."""
    timers = TimerService(notify)
    tools: list[Tool] = [
        SetTimerTool(timers),
        ListTimersTool(timers),
        CancelTimerTool(timers),
        SystemInfoTool(),
        WebSearchTool(settings, web_client),
    ]
    return ToolBox(tools), timers
