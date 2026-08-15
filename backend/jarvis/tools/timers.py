"""Timers and reminders that announce themselves when they elapse."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .base import JsonSchema, Notifier, ToolError, optional_number

MAX_TIMERS = 16
MAX_SECONDS = 24 * 60 * 60


@dataclass
class Timer:
    id: int
    label: str
    seconds: float
    task: asyncio.Task[None] = field(repr=False)


def humanize(seconds: float) -> str:
    total = int(round(seconds))
    if total < 60:
        return f"{total} second{'s' if total != 1 else ''}"
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs and not hours:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " ".join(parts)


class TimerService:
    """Owns the running timers for one session."""

    def __init__(self, notify: Notifier) -> None:
        self._notify = notify
        self._timers: dict[int, Timer] = {}
        self._next_id = 1

    @property
    def active(self) -> list[Timer]:
        return sorted(self._timers.values(), key=lambda timer: timer.id)

    def start(self, seconds: float, label: str) -> Timer:
        if seconds <= 0:
            raise ToolError("A timer needs a positive duration.")
        if seconds > MAX_SECONDS:
            raise ToolError("I can only set timers up to 24 hours.")
        if len(self._timers) >= MAX_TIMERS:
            raise ToolError("Too many timers are already running.")

        timer_id = self._next_id
        self._next_id += 1
        task = asyncio.create_task(self._run(timer_id, seconds))
        timer = Timer(id=timer_id, label=label, seconds=seconds, task=task)
        self._timers[timer_id] = timer
        return timer

    def cancel(self, timer_id: int | None) -> list[Timer]:
        targets = self.active if timer_id is None else [t for t in self.active if t.id == timer_id]
        if not targets:
            raise ToolError("No matching timer is running.")
        for timer in targets:
            timer.task.cancel()
            self._timers.pop(timer.id, None)
        return targets

    async def aclose(self) -> None:
        for timer in list(self._timers.values()):
            timer.task.cancel()
        self._timers.clear()

    async def _run(self, timer_id: int, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            raise
        timer = self._timers.pop(timer_id, None)
        if timer is None:
            return
        await self._notify(f"Your {timer.label} is up.")


class SetTimerTool:
    name = "set_timer"
    description = (
        "Start a countdown timer or reminder. Announces itself out loud when it elapses. "
        "Give the duration in seconds, or minutes/hours."
    )
    parameters: JsonSchema = {
        "type": "object",
        "properties": {
            "seconds": {"type": "number", "description": "Duration in seconds."},
            "minutes": {"type": "number", "description": "Duration in minutes."},
            "hours": {"type": "number", "description": "Duration in hours."},
            "label": {"type": "string", "description": "What the timer is for, e.g. 'tea'."},
        },
    }

    def __init__(self, service: TimerService) -> None:
        self._service = service

    async def run(self, arguments: Mapping[str, object]) -> str:
        seconds = optional_number(arguments, "seconds") or 0.0
        seconds += (optional_number(arguments, "minutes") or 0.0) * 60
        seconds += (optional_number(arguments, "hours") or 0.0) * 3600
        if seconds <= 0:
            raise ToolError("Tell me how long the timer should run.")
        raw_label = arguments.get("label")
        label = raw_label.strip() if isinstance(raw_label, str) and raw_label.strip() else "timer"
        timer = self._service.start(seconds, label)
        return f"Timer {timer.id} set for {humanize(seconds)} ({timer.label})."


class ListTimersTool:
    name = "list_timers"
    description = "List the timers that are currently running."
    parameters: JsonSchema = {"type": "object", "properties": {}}

    def __init__(self, service: TimerService) -> None:
        self._service = service

    async def run(self, arguments: Mapping[str, object]) -> str:
        timers = self._service.active
        if not timers:
            return "No timers are running."
        return "; ".join(f"{t.id}: {t.label} ({humanize(t.seconds)})" for t in timers)


class CancelTimerTool:
    name = "cancel_timer"
    description = "Cancel a running timer by id, or every timer when no id is given."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {"id": {"type": "integer", "description": "Timer id to cancel."}},
    }

    def __init__(self, service: TimerService) -> None:
        self._service = service

    async def run(self, arguments: Mapping[str, object]) -> str:
        raw = optional_number(arguments, "id")
        cancelled = self._service.cancel(int(raw) if raw is not None else None)
        if len(cancelled) == 1:
            return f"Cancelled timer {cancelled[0].id} ({cancelled[0].label})."
        return f"Cancelled {len(cancelled)} timers."


_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|s|m|h)\b")
_UNIT_SECONDS = {"s": 1.0, "m": 60.0, "h": 3600.0}
_REMINDER = re.compile(r"remind me to (.+?)(?:\s+in\b|\s+after\b|$)")
_NAMED_TIMER = re.compile(r"\b(?:a|an|my|the)?\s*([a-z]+)\s+timer\b")


def parse_duration(text: str) -> tuple[float, str] | None:
    """Parse a spoken timer request such as ``set a tea timer for 5 minutes``."""
    match = _DURATION.search(text)
    if not match:
        return None
    seconds = float(match.group(1)) * _UNIT_SECONDS[match.group(2)[0]]

    reminder = _REMINDER.search(text)
    if reminder:
        return seconds, reminder.group(1).strip()
    named = _NAMED_TIMER.search(text)
    if named and named.group(1) not in {"a", "an", "my", "the"}:
        return seconds, f"{named.group(1)} timer"
    return seconds, "timer"
