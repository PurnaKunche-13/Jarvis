"""Chooses the provider set for the current configuration."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from .config import Settings
from .providers.base import LLMProvider, STTProvider, TTSProvider
from .providers.local import LocalLLM, UnavailableSTT, UnavailableTTS
from .providers.openai_compat import OpenAICompatLLM, OpenAICompatSTT, OpenAICompatTTS
from .schemas import RuntimeConfig


@dataclass
class Runtime:
    settings: Settings
    llm: LLMProvider
    stt: STTProvider
    tts: TTSProvider
    client: httpx.AsyncClient | None

    def describe(self) -> RuntimeConfig:
        return RuntimeConfig(
            wake_word=self.settings.wake_word,
            cloud_enabled=self.settings.cloud_enabled,
            server_tts=self.tts.available,
            server_stt=self.stt.available,
            chat_model=self.settings.chat_model if self.settings.cloud_enabled else self.llm.name,
        )

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()


def build_runtime(settings: Settings) -> Runtime:
    if not settings.cloud_enabled:
        return Runtime(
            settings=settings,
            llm=LocalLLM(),
            stt=UnavailableSTT(),
            tts=UnavailableTTS(),
            client=None,
        )

    client = httpx.AsyncClient(
        base_url=settings.api_base,
        headers={"Authorization": f"Bearer {settings.api_key}"},
        timeout=httpx.Timeout(settings.request_timeout),
    )
    tts: TTSProvider = (
        OpenAICompatTTS(settings, client) if settings.server_tts else UnavailableTTS()
    )
    return Runtime(
        settings=settings,
        llm=OpenAICompatLLM(settings, client),
        stt=OpenAICompatSTT(settings, client),
        tts=tts,
        client=client,
    )
