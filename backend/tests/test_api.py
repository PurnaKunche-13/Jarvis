from __future__ import annotations

from fastapi.testclient import TestClient

from jarvis.app import create_app


def test_healthz_and_config() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        config = client.get("/api/config").json()
        assert config["wake_word"] == "jarvis"
        assert config["cloud_enabled"] is False
        assert config["server_stt"] is False


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
            if event["type"] == "state" and event["value"] == "idle":
                break
        reply = next(event for event in events if event["type"] == "reply_end")
        assert reply["text"] == "42"

        socket.send_json({"type": "bogus"})
        assert socket.receive_json()["type"] == "error"
