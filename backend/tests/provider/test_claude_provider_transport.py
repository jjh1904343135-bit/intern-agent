from __future__ import annotations

import asyncio

from app.core.providers.claude_provider import ClaudeProvider
from app.core.settings import settings


def test_claude_provider_prefers_ollama_chat_transport(monkeypatch) -> None:
    original_transport = getattr(settings, "claude_transport", "ollama_chat")
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    try:
        settings.claude_transport = "ollama_chat"
        settings.claude_api_key = "sk-local"
        settings.claude_base_url = "http://model.example/v"
        settings.claude_model = "gemma4:26b"

        provider = ClaudeProvider()
        captured: dict[str, object] = {}

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            captured["url"] = url
            captured["payload"] = payload
            return {"message": {"content": "面试前先复盘项目，再补数据结构与数据库基础。"}}

        monkeypatch.setattr(provider, "_post_json", fake_post_json)
        result = asyncio.run(
            provider.generate(
                "请用两句话总结后端实习面试前要准备什么。",
                system_prompt="你是中文求职教练，请输出自然中文。",
            )
        )

        assert result.startswith("面试前")
        assert captured["url"] == "http://model.example/api/chat"
        assert captured["payload"]["think"] is False
        assert captured["payload"]["options"]["num_predict"] == 512
        assert captured["payload"]["messages"][0]["role"] == "system"
    finally:
        settings.claude_transport = original_transport
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model


def test_claude_provider_maps_max_tokens_to_ollama_num_predict(monkeypatch) -> None:
    original_transport = getattr(settings, "claude_transport", "ollama_chat")
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    try:
        settings.claude_transport = "ollama_chat"
        settings.claude_api_key = "sk-local"
        settings.claude_base_url = "http://model.example/v"
        settings.claude_model = "gemma4:26b"

        provider = ClaudeProvider()
        captured: dict[str, object] = {}

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            captured["payload"] = payload
            return {"message": {"content": "连接正常"}}

        monkeypatch.setattr(provider, "_post_json", fake_post_json)
        result = asyncio.run(provider.generate("请只回复连接正常", max_tokens=24))

        assert result == "连接正常"
        assert captured["payload"]["options"]["num_predict"] == 24
    finally:
        settings.claude_transport = original_transport
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model


def test_claude_provider_diagnose_checks_short_generation(monkeypatch) -> None:
    original_transport = getattr(settings, "claude_transport", "ollama_chat")
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    try:
        settings.claude_transport = "ollama_chat"
        settings.claude_api_key = "sk-local"
        settings.claude_base_url = "http://model.example/v"
        settings.claude_model = "gemma4:26b"

        provider = ClaudeProvider()
        captured: dict[str, object] = {}

        async def fake_get_json(*, url: str) -> dict:
            return {"models": [{"name": "gemma4:26b"}]}

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            captured["url"] = url
            captured["payload"] = payload
            return {"message": {"content": "ok"}}

        monkeypatch.setattr(provider, "_get_json", fake_get_json)
        monkeypatch.setattr(provider, "_post_json", fake_post_json)

        diagnostics = asyncio.run(provider.diagnose())

        assert diagnostics["reachable"] is True
        assert diagnostics["tag_reachable"] is True
        assert diagnostics["generation_reachable"] is True
        assert captured["url"] == "http://model.example/api/chat"
        assert captured["payload"]["options"]["num_predict"] == 8
    finally:
        settings.claude_transport = original_transport
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model


def test_claude_provider_diagnose_uses_streaming_for_ollama_generate(monkeypatch) -> None:
    original_transport = getattr(settings, "claude_transport", "ollama_chat")
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    try:
        settings.claude_transport = "ollama_generate"
        settings.claude_api_key = "sk-local"
        settings.claude_base_url = "http://model.example/v"
        settings.claude_model = "gemma4:26b"

        provider = ClaudeProvider()
        captured: dict[str, object] = {}

        async def fake_get_json(*, url: str) -> dict:
            return {"models": [{"name": "gemma4:26b"}]}

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            raise AssertionError("diagnose must not use full JSON for ollama_generate")

        async def fake_post_stream(*, url: str, payload: dict, headers: dict[str, str]):
            captured["url"] = url
            captured["payload"] = payload
            yield "ok"

        monkeypatch.setattr(provider, "_get_json", fake_get_json)
        monkeypatch.setattr(provider, "_post_json", fake_post_json)
        monkeypatch.setattr(provider, "_post_stream", fake_post_stream)

        diagnostics = asyncio.run(provider.diagnose())

        assert diagnostics["reachable"] is True
        assert diagnostics["generation_reachable"] is True
        assert captured["url"] == "http://model.example/api/generate"
        assert captured["payload"]["stream"] is True
        assert captured["payload"]["options"]["num_predict"] == 8
    finally:
        settings.claude_transport = original_transport
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model


def test_claude_provider_generate_uses_streaming_for_ollama_generate(monkeypatch) -> None:
    original_transport = getattr(settings, "claude_transport", "ollama_chat")
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = settings.claude_model
    try:
        settings.claude_transport = "ollama_generate"
        settings.claude_api_key = "sk-local"
        settings.claude_base_url = "http://model.example/v"
        settings.claude_model = "gemma4:26b"

        provider = ClaudeProvider()
        captured: dict[str, object] = {}

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            raise AssertionError("Ollama generate should be consumed as a stream to avoid read timeouts")

        async def fake_post_stream(*, url: str, payload: dict, headers: dict[str, str]):
            captured["url"] = url
            captured["payload"] = payload
            yield "连接"
            yield "正常"

        monkeypatch.setattr(provider, "_post_json", fake_post_json)
        monkeypatch.setattr(provider, "_post_stream", fake_post_stream)
        result = asyncio.run(provider.generate("请只回复连接正常", max_tokens=16))

        assert result == "连接正常"
        assert captured["url"] == "http://model.example/api/generate"
        assert captured["payload"]["stream"] is True
        assert captured["payload"]["options"]["num_predict"] == 16
    finally:
        settings.claude_transport = original_transport
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model


def test_claude_provider_uses_safe_minimum_timeout_for_remote_model() -> None:
    original_timeout = settings.claude_timeout_seconds
    try:
        settings.claude_timeout_seconds = 8
        provider = ClaudeProvider()
        timeout = provider._timeout()

        assert timeout.read >= 120
        assert timeout.connect >= 3
    finally:
        settings.claude_timeout_seconds = original_timeout
