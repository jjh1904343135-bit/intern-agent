from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.core.providers.base import LLMProvider
from app.services.streaming import chunk_text


class MockProvider(LLMProvider):
    @property
    def name(self) -> str:
        return "mock"

    @property
    def model(self) -> str:
        return "mock-local"

    @property
    def transport(self) -> str:
        return "mock"

    @property
    def supports_stream(self) -> bool:
        return True

    async def diagnose(self) -> dict[str, Any]:
        return {"reachable": True, "last_error": None}

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        # Deterministic output for local verification without external API keys.
        return f"[MOCK_RESPONSE] {prompt[:120]}"

    async def stream_generate(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        for chunk in chunk_text(await self.generate(prompt, **kwargs), size=16):
            yield chunk
