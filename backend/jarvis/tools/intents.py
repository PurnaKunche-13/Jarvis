"""Phrase matching so the offline brain can reach the same tools as the model.

The cloud path lets the model pick tools; without a model we recognise the
handful of phrasings people actually use.
"""

from __future__ import annotations

import re

from .timers import parse_duration

ToolCall = tuple[str, dict[str, object]]

_SET_TIMER = re.compile(r"\b(?:set|start)\b.*\b(?:timer|alarm)\b|\bremind me\b|\btimer for\b")
_LIST_TIMERS = re.compile(r"\b(?:what|which|list|any|how many)\b.*\btimers?\b")
_CANCEL_TIMER = re.compile(r"\b(?:cancel|stop|clear|kill)\b.*\b(?:timer|alarm)s?\b")
_CANCEL_ID = re.compile(r"\btimer\s+(\d+)\b|\bnumber\s+(\d+)\b")
_SYSTEM_INFO = re.compile(
    r"\bsystem (?:info|status|stats)\b|\b(?:cpu|memory|ram|disk|uptime|load)\b"
    r"|\bhow (?:are you feeling|is the (?:server|machine|system))\b"
)
_SEARCH = re.compile(
    r"^(?:please\s+)?(?:"
    r"search(?:\s+(?:the\s+web|online))?(?:\s+for)?"
    r"|google|look\s+up|find\s+out(?:\s+about)?"
    r")\s+(.+)"
)


def match_intent(prompt: str) -> ToolCall | None:
    """Map a spoken command onto a tool call, or return ``None``."""
    text = prompt.strip().rstrip("?.!")
    lowered = text.lower()

    if _CANCEL_TIMER.search(lowered):
        match = _CANCEL_ID.search(lowered)
        if match:
            return "cancel_timer", {"id": int(match.group(1) or match.group(2))}
        return "cancel_timer", {}
    if _LIST_TIMERS.search(lowered):
        return "list_timers", {}
    if _SET_TIMER.search(lowered):
        parsed = parse_duration(lowered)
        if parsed is not None:
            seconds, label = parsed
            return "set_timer", {"seconds": seconds, "label": label}
    if _SYSTEM_INFO.search(lowered):
        return "system_info", {}
    search = _SEARCH.match(lowered)
    if search:
        query = search.group(1).strip()
        if query:
            return "web_search", {"query": query, "limit": 3}
    return None
