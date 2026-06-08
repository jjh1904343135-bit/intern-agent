from __future__ import annotations

import asyncio

from app.core.providers.claude_provider import ClaudeProvider
from app.core.settings import settings


def test_claude_provider_generate_reads_openai_compatible_response(monkeypatch) -> None:
    original_provider = settings.llm_provider
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = getattr(settings, 'claude_model', None)
    original_transport = getattr(settings, 'claude_transport', 'ollama_chat')
    try:
        settings.llm_provider = 'claude'
        settings.claude_api_key = 'sk-local'
        settings.claude_base_url = 'http://model.example/v'
        settings.claude_model = 'gemma4:26b'
        settings.claude_transport = 'openai_chat'

        provider = ClaudeProvider()
        captured: dict[str, object] = {}

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            captured['url'] = url
            captured['payload'] = payload
            captured['headers'] = headers
            return {'choices': [{'message': {'content': '来自真实模型的回答'}}]}

        monkeypatch.setattr(provider, '_post_json', fake_post_json)
        result = asyncio.run(provider.generate('请总结 FastAPI 项目亮点', system_prompt='你是求职助手'))

        assert result == '来自真实模型的回答'
        assert str(captured['url']).endswith('/v1/chat/completions')
        assert captured['payload']['model'] == 'gemma4:26b'
        assert captured['payload']['messages'][0]['role'] == 'system'
    finally:
        settings.llm_provider = original_provider
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model
        settings.claude_transport = original_transport


def test_claude_provider_generate_falls_back_to_ollama_chat(monkeypatch) -> None:
    original_provider = settings.llm_provider
    original_key = settings.claude_api_key
    original_base_url = settings.claude_base_url
    original_model = getattr(settings, 'claude_model', None)
    original_transport = getattr(settings, 'claude_transport', 'ollama_chat')
    try:
        settings.llm_provider = 'claude'
        settings.claude_api_key = 'sk-local'
        settings.claude_base_url = 'http://model.example/v'
        settings.claude_model = 'gemma4:26b'
        settings.claude_transport = 'auto'

        provider = ClaudeProvider()
        called_urls: list[str] = []
        streamed_urls: list[str] = []

        async def fake_post_json(*, url: str, payload: dict, headers: dict[str, str]) -> dict:
            called_urls.append(url)
            if url.endswith('/api/chat'):
                raise RuntimeError('ollama-chat endpoint unavailable')
            return {'message': {'content': '来自 Ollama generate 接口'}}

        async def fake_post_stream(*, url: str, payload: dict, headers: dict[str, str]):
            streamed_urls.append(url)
            yield '来自 Ollama generate 接口'

        monkeypatch.setattr(provider, '_post_json', fake_post_json)
        monkeypatch.setattr(provider, '_post_stream', fake_post_stream)
        result = asyncio.run(provider.generate('请模拟一段面试反馈'))

        assert result == '来自 Ollama generate 接口'
        assert called_urls[0].endswith('/api/chat')
        assert streamed_urls[0].endswith('/api/generate')
    finally:
        settings.llm_provider = original_provider
        settings.claude_api_key = original_key
        settings.claude_base_url = original_base_url
        settings.claude_model = original_model
        settings.claude_transport = original_transport
