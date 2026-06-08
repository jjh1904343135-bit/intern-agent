from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.services.streaming import chunk_text


class LLMProvider(ABC):
    """Provider abstraction kept stable from Day 1 so model vendors can be swapped later."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    def configured(self) -> bool:
        return False

    @property
    def supports_stream(self) -> bool:
        return False

    @property
    def base_url(self) -> str | None:
        return None

    @property
    def model(self) -> str | None:
        return None

    @property
    def transport(self) -> str | None:
        return None

    async def diagnose(self) -> dict[str, Any]:
        return {
            "reachable": self.configured,
            "last_error": None if self.configured else "provider not configured",
        }

    @abstractmethod
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    async def stream_generate(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        """Compatibility streaming: providers without native stream still expose chunked output."""
        content = await self.generate(prompt, **kwargs)
        for chunk in chunk_text(content):
            yield chunk
