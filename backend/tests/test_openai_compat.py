from __future__ import annotations

import json
from collections.abc import Mapping

import httpx

from jarvis.config import Settings
from jarvis.providers.openai_compat import OpenAICompatLLM
from jarvis.tools import ToolBox
from jarvis.tools.base import JsonSchema


class EchoTool:
    name = "echo"
    description = "Echo the text back."
    parameters: JsonSchema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    def __init__(self) -> None:
        self.calls: list[Mapping[str, object]] = []

    async def run(self, arguments: Mapping[str, object]) -> str:
        self.calls.append(arguments)
        return f"echo:{arguments['text']}"


def sse(*deltas: Mapping[str, object]) -> str:
    lines = [f"data: {json.dumps({'choices': [{'delta': delta}]})}" for delta in deltas]
    return "\n\n".join([*lines, "data: [DONE]", ""])


async def test_streamed_tool_call_is_executed_then_the_answer_streams() -> None:
    tool = EchoTool()
    box = ToolBox([tool])
    payloads: list[dict[str, object]] = []
    bodies = [
        sse(
            {"tool_calls": [{"index": 0, "id": "call_a", "function": {"name": "ec"}}]},
            {"tool_calls": [{"index": 0, "function": {"name": "ho", "arguments": '{"te'}}]},
            {"tool_calls": [{"index": 0, "function": {"arguments": 'xt": "hi"}'}}]},
        ),
        sse({"content": "You "}, {"content": "said hi."}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, text=bodies[len(payloads) - 1])

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.test/v1"
    )
    llm = OpenAICompatLLM(Settings(), client)

    fragments = [
        fragment async for fragment in llm.stream([{"role": "user", "content": "hi"}], box)
    ]

    assert "".join(fragments) == "You said hi."
    assert tool.calls == [{"text": "hi"}]
    assert payloads[0]["tool_choice"] == "auto"
    follow_up = payloads[1]["messages"]
    assert isinstance(follow_up, list)
    assert follow_up[-2]["tool_calls"][0]["id"] == "call_a"
    assert follow_up[-1] == {
        "role": "tool",
        "content": "echo:hi",
        "tool_call_id": "call_a",
    }


async def test_plain_reply_makes_one_request_and_omits_tools_when_empty() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, text=sse({"content": "At once."}))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.test/v1"
    )
    llm = OpenAICompatLLM(Settings(), client)

    fragments = [
        fragment async for fragment in llm.stream([{"role": "user", "content": "hi"}], ToolBox([]))
    ]

    assert "".join(fragments) == "At once."
    assert len(payloads) == 1
    assert "tools" not in payloads[0]


async def test_tool_rounds_are_bounded() -> None:
    tool = EchoTool()
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            text=sse(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_a",
                            "function": {"name": "echo", "arguments": '{"text": "loop"}'},
                        }
                    ]
                }
            ),
        )

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.test/v1"
    )
    llm = OpenAICompatLLM(Settings(max_tool_rounds=2), client)

    async for _ in llm.stream([{"role": "user", "content": "hi"}], ToolBox([tool])):
        pass

    assert requests == 2
