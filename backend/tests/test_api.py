from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from jarvis.app import create_app


def test_healthz_and_config() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        config = client.get("/api/config").json()
        assert config["wake_word"] == "jarvis"
        assert config["cloud_enabled"] is False
        assert config["server_stt"] is False
        assert "set_timer" in config["tools"] and "web_search" in config["tools"]


def test_websocket_turn_without_api_key() -> None:
    with TestClient(create_app()) as client, client.websocket_connect("/ws") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "hello"
        assert hello["config"]["wake_word"] == "jarvis"

        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}

        socket.send_json({"type": "user_text", "text": "what is 6 times 7"})
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event["type"] == "reply_end":
                break
        assert events[-1]["text"] == "42"
        # The browser speaks, so the client owns the return to idle.
        assert events[-1]["speak"] is True

        socket.send_json({"type": "bogus"})
        seen: list[str] = []
        while "error" not in seen:
            seen.append(socket.receive_json()["type"])


def test_websocket_rejects_foreign_origin() -> None:
    client = TestClient(create_app())
    headers = {"origin": "https://evil.example"}
    with (
        client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers=headers) as socket,
    ):
        socket.receive_json()


def test_websocket_survives_malformed_frame() -> None:
    with TestClient(create_app()) as client, client.websocket_connect("/ws") as socket:
        socket.receive_json()
        socket.send_text("not json")
        assert socket.receive_json() == {"type": "error", "message": "Malformed frame."}
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}
