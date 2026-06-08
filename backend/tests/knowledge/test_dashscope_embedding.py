from __future__ import annotations

import httpx
import pytest

from app.tools.embeddings.dashscope_adapter import DashScopeEmbeddingClient, EmbeddingProviderError, EmbeddingProviderNotConfigured


def test_dashscope_embedding_requires_api_key() -> None:
    client = DashScopeEmbeddingClient(api_key="", base_url="https://dashscope.example", model="text-embedding-v4", dimensions=1024)

    with pytest.raises(EmbeddingProviderNotConfigured, match="DASHSCOPE_API_KEY"):
        client.embed_texts(["JVM memory model"])


def test_dashscope_embedding_uses_dashscope_native_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"output": {"embeddings": [{"embedding": [0.1] * 1024}, {"embedding": [0.2] * 1024}]}}

    class FakeClient:
        def __init__(self, *, timeout: int) -> None:
            captured["timeout"] = timeout

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.tools.embeddings.dashscope_adapter.httpx.Client", FakeClient)

    client = DashScopeEmbeddingClient(api_key="sk-test", base_url="https://dashscope.example/", model="text-embedding-v4", dimensions=1024)
    vectors = client.embed_texts(["JVM memory model", "Redis speed"])

    assert len(vectors) == 2
    assert all(len(vector) == 1024 for vector in vectors)
    assert captured["url"] == "https://dashscope.example/api/v1/services/embeddings/text-embedding/text-embedding"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"] == {
        "model": "text-embedding-v4",
        "input": {"texts": ["JVM memory model", "Redis speed"]},
        "parameters": {"dimension": 1024},
    }


def test_dashscope_embedding_surfaces_business_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        text = '{"error":{"code":"AccessDenied.Unpurchased","message":"Access to model denied"}}'

        def raise_for_status(self) -> None:
            request = httpx.Request("POST", "https://dashscope.example/api/v1/services/embeddings/text-embedding/text-embedding")
            response = httpx.Response(400, request=request, text=self.text)
            raise httpx.HTTPStatusError("bad request", request=request, response=response)

    class FakeClient:
        def __init__(self, *, timeout: int) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr("app.tools.embeddings.dashscope_adapter.httpx.Client", FakeClient)
    client = DashScopeEmbeddingClient(api_key="sk-test", base_url="https://dashscope.example", model="text-embedding-v4", dimensions=1024)

    with pytest.raises(EmbeddingProviderError, match="AccessDenied.Unpurchased"):
        client.embed_texts(["JVM memory model"])


def test_dashscope_embedding_splits_batch_when_connection_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class FakeResponse:
        def __init__(self, texts: list[str]) -> None:
            self.texts = texts

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"output": {"embeddings": [{"embedding": [float(index + 1)] * 1024} for index, _ in enumerate(self.texts)]}}

    class FakeClient:
        def __init__(self, *, timeout: int) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
            texts = json["input"]["texts"]
            calls.append(list(texts))
            if len(texts) > 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return FakeResponse(texts)

    monkeypatch.setattr("app.tools.embeddings.dashscope_adapter.httpx.Client", FakeClient)
    client = DashScopeEmbeddingClient(api_key="sk-test", base_url="https://dashscope.example", model="text-embedding-v4", dimensions=1024)

    vectors = client.embed_texts(["JVM memory model", "Redis speed"])

    assert len(vectors) == 2
    assert all(len(vector) == 1024 for vector in vectors)
    assert calls == [["JVM memory model", "Redis speed"], ["JVM memory model"], ["Redis speed"]]


def test_dashscope_embedding_retries_single_text_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"output": {"embeddings": [{"embedding": [0.3] * 1024}]}}

    class FakeClient:
        def __init__(self, *, timeout: int) -> None:
            return None

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs) -> FakeResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
            return FakeResponse()

    monkeypatch.setattr("app.tools.embeddings.dashscope_adapter.httpx.Client", FakeClient)
    monkeypatch.setattr("app.tools.embeddings.dashscope_adapter.time.sleep", lambda seconds: None)
    client = DashScopeEmbeddingClient(api_key="sk-test", base_url="https://dashscope.example", model="text-embedding-v4", dimensions=1024)

    vectors = client.embed_texts(["JVM memory model"])

    assert len(vectors) == 1
    assert calls == 2
