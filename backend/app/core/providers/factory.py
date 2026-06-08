from app.core.providers.base import LLMProvider
from app.core.providers.claude_provider import ClaudeProvider
from app.core.providers.mock_provider import MockProvider
from app.core.settings import settings


def get_provider() -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unsupported provider: {settings.llm_provider}")
