"""FastAPI application exposing the Jarvis websocket."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, TypeAdapter, ValidationError

from .config import load_settings
from .registry import Runtime, build_runtime
from .schemas import (
    ClientAudio,
    ClientMessage,
    ClientPing,
    ClientReset,
    ClientText,
    RuntimeConfig,
    ServerError,
    ServerHello,
    ServerPong,
    ServerState,
)
from .session import Session

logger = logging.getLogger(__name__)

_client_message = TypeAdapter[ClientMessage](ClientMessage)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    runtime = build_runtime(load_settings())
    app.state.runtime = runtime
    logger.info(
        "jarvis online (llm=%s stt=%s tts=%s)",
        runtime.llm.name,
        runtime.stt.name,
        runtime.tts.name,
    )
    try:
        yield
    finally:
        await runtime.aclose()


def create_app() -> FastAPI:
    app = FastAPI(title="Jarvis", version="0.1.0", lifespan=lifespan)
    settings = load_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # Credentials plus a wildcard origin would let any site read the API.
        allow_credentials=not settings.open_cors,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config", response_model=RuntimeConfig)
    async def config() -> RuntimeConfig:
        runtime: Runtime = app.state.runtime
        return runtime.describe()

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        runtime: Runtime = app.state.runtime
        # Websocket handshakes skip the CORS middleware, so any page could drive
        # this socket (and spend the operator's API key) without this check.
        if not runtime.settings.origin_allowed(socket.headers.get("origin")):
            await socket.close(code=1008)
            return
        await socket.accept()
        session = Session(runtime, lambda message: socket.send_json(_dump(message)))
        await socket.send_json(_dump(ServerHello(config=runtime.describe())))
        try:
            while True:
                try:
                    raw = await socket.receive_json()
                except json.JSONDecodeError:
                    await socket.send_json(_dump(ServerError(message="Malformed frame.")))
                    continue
                try:
                    message = _client_message.validate_python(raw)
                except ValidationError:
                    await socket.send_json(_dump(ServerError(message="Unrecognised message.")))
                    continue
                await _dispatch(session, socket, message)
        except WebSocketDisconnect:
            logger.debug("client disconnected")
        finally:
            await session.aclose()

    return app


async def _dispatch(session: Session, socket: WebSocket, message: ClientMessage) -> None:
    if isinstance(message, ClientPing):
        await socket.send_json(_dump(ServerPong()))
    elif isinstance(message, ClientReset):
        session.reset()
        await socket.send_json(_dump(ServerState(value="idle")))
    elif isinstance(message, ClientText):
        await session.handle_text(message.text)
    elif isinstance(message, ClientAudio):
        await session.handle_audio(message.audio, message.mime)
    else:  # ClientCancel
        await socket.send_json(_dump(ServerState(value="idle")))


def _dump(message: BaseModel) -> dict[str, object]:
    return dict(message.model_dump())


app = create_app()
