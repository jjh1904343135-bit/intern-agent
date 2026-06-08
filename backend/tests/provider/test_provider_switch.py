from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.providers.claude_provider import ClaudeProvider
from app.core.providers.factory import get_provider
from app.core.settings import settings
from app.main import app

client = TestClient(app)


def test_provider_defaults_to_mock() -> None:
    original_provider = settings.llm_provider
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    try:
        settings.llm_provider = "mock"
        settings.claude_api_key = None
        settings.claude_base_url = None
        provider = get_provider()
        assert provider.name == "mock"

        response = client.get("/health/provider")
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "mock"
        assert body["configured"] is False
        assert body["supports_stream"] is True
        assert body["model"] == "mock-local"
        assert body["transport"] == "mock"
    finally:
        settings.llm_provider = original_provider
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url


def test_provider_switches_to_claude_when_configured() -> None:
    original_provider = settings.llm_provider
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    original_transport = settings.claude_transport
    try:
        settings.llm_provider = "claude"
        settings.claude_api_key = "test-claude-key"
        settings.claude_base_url = "https://api.anthropic.example"
        settings.claude_model = "gemma4:26b"
        settings.claude_transport = "ollama_chat"
        provider = get_provider()
        assert provider.name == "claude"

        response = client.get("/health/provider")
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "claude"
        assert body["configured"] is True
        assert body["supports_stream"] is True
        assert body["base_url"] == "https://api.anthropic.example"
        assert body["model"] == "gemma4:26b"
        assert body["transport"] == "ollama_chat"
    finally:
        settings.llm_provider = original_provider
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model
        settings.claude_transport = original_transport


def test_provider_health_exposes_reachability_details(monkeypatch) -> None:
    original_provider = settings.llm_provider
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    original_transport = settings.claude_transport
    try:
        settings.llm_provider = "claude"
        settings.claude_api_key = "sk-local"
        settings.claude_base_url = "http://model.example/v"
        settings.claude_model = "gemma4:26b"
        settings.claude_transport = "ollama_chat"

        async def fake_diagnose(self) -> dict:
            return {"reachable": False, "last_error": "model not found"}

        monkeypatch.setattr(ClaudeProvider, "diagnose", fake_diagnose, raising=False)

        response = client.get("/health/provider")
        assert response.status_code == 200
        body = response.json()
        assert body["reachable"] is False
        assert body["last_error"] == "model not found"
    finally:
        settings.llm_provider = original_provider
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model
        settings.claude_transport = original_transport
