"""Runtime configuration, sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_SYSTEM_PROMPT = (
    "You are JARVIS, a concise, unflappable assistant. "
    "Answer in one or two sentences unless asked for detail. "
    "Never mention that you are an AI language model."
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the process configuration."""

    host: str = field(default_factory=lambda: os.getenv("JARVIS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("JARVIS_PORT", "8000")))
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "JARVIS_CORS_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]
        )
    )

    # OpenAI-compatible endpoint. Works with OpenAI, Azure gateways, Ollama,
    # LM Studio, vLLM and anything else speaking the same REST shape.
    api_key: str | None = field(default_factory=lambda: os.getenv("JARVIS_API_KEY"))
    api_base: str = field(
        default_factory=lambda: os.getenv("JARVIS_API_BASE", "https://api.openai.com/v1").rstrip("/")
    )
    chat_model: str = field(default_factory=lambda: os.getenv("JARVIS_CHAT_MODEL", "gpt-4o-mini"))
    stt_model: str = field(default_factory=lambda: os.getenv("JARVIS_STT_MODEL", "whisper-1"))
    tts_model: str = field(default_factory=lambda: os.getenv("JARVIS_TTS_MODEL", "gpt-4o-mini-tts"))
    tts_voice: str = field(default_factory=lambda: os.getenv("JARVIS_TTS_VOICE", "onyx"))

    system_prompt: str = field(
        default_factory=lambda: os.getenv("JARVIS_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
    )
    wake_word: str = field(default_factory=lambda: os.getenv("JARVIS_WAKE_WORD", "jarvis"))
    history_turns: int = field(default_factory=lambda: int(os.getenv("JARVIS_HISTORY_TURNS", "12")))
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("JARVIS_REQUEST_TIMEOUT", "60"))
    )
    server_tts: bool = field(default_factory=lambda: _env_bool("JARVIS_SERVER_TTS", True))

    @property
    def cloud_enabled(self) -> bool:
        """True when a remote OpenAI-compatible endpoint can be reached."""
        return bool(self.api_key)


def load_settings() -> Settings:
    return Settings()
