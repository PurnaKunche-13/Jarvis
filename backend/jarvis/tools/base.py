"""Tool contract shared by the LLM function-calling path and the local brain."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

JsonSchema = Mapping[str, object]

#: Called by a tool to push an unsolicited message (e.g. a timer firing).
Notifier = Callable[[str], Awaitable[None]]


@runtime_checkable
class Tool(Protocol):
    name: str
    description: str
    parameters: JsonSchema

    async def run(self, arguments: Mapping[str, object]) -> str:
        """Execute the tool and return a short result for the model or the user."""


class ToolError(RuntimeError):
    """Raised when a tool cannot complete; the message is shown to the model."""


class ToolBox:
    """A session's tools, addressable by name."""

    def __init__(self, tools: Sequence[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, object]]:
        """OpenAI-style function specs."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    async def invoke(self, name: str, arguments: Mapping[str, object]) -> str:
        """Run a tool, converting failures into text the caller can speak."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Unknown tool: {name}"
        try:
            return await tool.run(arguments)
        except ToolError as exc:
            return str(exc)
        except Exception:
            logger.exception("tool %s failed", name)
            return f"The {name} tool failed."

    async def invoke_json(self, name: str, raw_arguments: str) -> str:
        """Run a tool with the JSON argument string a model produced."""
        try:
            parsed = json.loads(raw_arguments) if raw_arguments.strip() else {}
        except json.JSONDecodeError:
            return f"Malformed arguments for {name}."
        if not isinstance(parsed, dict):
            return f"Arguments for {name} must be an object."
        return await self.invoke(name, parsed)


def require_str(arguments: Mapping[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"Missing required argument: {key}")
    return value.strip()


def optional_number(arguments: Mapping[str, object], key: str) -> float | None:
    value = arguments.get(key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ToolError(f"Argument {key} must be a number")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError as exc:
            raise ToolError(f"Argument {key} must be a number") from exc
    raise ToolError(f"Argument {key} must be a number")
