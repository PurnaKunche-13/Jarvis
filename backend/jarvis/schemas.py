"""Wire format shared by the backend and the hologram client."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AssistantState = Literal["idle", "listening", "thinking", "speaking"]


class ClientText(BaseModel):
    type: Literal["user_text"]
    text: str = Field(min_length=1, max_length=4000)


class ClientAudio(BaseModel):
    """A complete utterance, base64 encoded, recorded by the browser."""

    type: Literal["user_audio"]
    audio: str
    mime: str = "audio/webm"


class ClientCancel(BaseModel):
    type: Literal["cancel"]


class ClientReset(BaseModel):
    type: Literal["reset"]


class ClientPing(BaseModel):
    type: Literal["ping"]


ClientMessage = ClientText | ClientAudio | ClientCancel | ClientReset | ClientPing


class ServerState(BaseModel):
    type: Literal["state"] = "state"
    value: AssistantState


class ServerTranscript(BaseModel):
    type: Literal["transcript"] = "transcript"
    text: str


class ServerToken(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ServerReplyEnd(BaseModel):
    type: Literal["reply_end"] = "reply_end"
    text: str
    speak: bool = True


class ServerAudio(BaseModel):
    type: Literal["audio"] = "audio"
    audio: str
    mime: str = "audio/mpeg"


class ServerError(BaseModel):
    type: Literal["error"] = "error"
    message: str


class ServerPong(BaseModel):
    type: Literal["pong"] = "pong"


class RuntimeConfig(BaseModel):
    """Handed to the client on connect so the UI can adapt itself."""

    wake_word: str
    cloud_enabled: bool
    server_tts: bool
    server_stt: bool
    chat_model: str


class ServerHello(BaseModel):
    type: Literal["hello"] = "hello"
    config: RuntimeConfig
