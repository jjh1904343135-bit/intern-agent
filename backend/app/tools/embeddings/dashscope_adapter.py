"""DashScope embedding adapter for the AI assistant knowledge base."""

from __future__ import annotations

import httpx
import time


class EmbeddingProviderNotConfigured(RuntimeError):
    """Raised when a configured embedding provider is missing credentials."""


class EmbeddingProviderError(RuntimeError):
    """Raised when the embedding API returns an invalid response."""


class DashScopeEmbeddingClient:
    """Call DashScope's native text embedding endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        dimensions: int,
        timeout_seconds: int = 60,
        network_retries: int = 3,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.network_retries = max(1, network_retries)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise EmbeddingProviderNotConfigured("DASHSCOPE_API_KEY is required when EMBEDDING_PROVIDER=dashscope")
        if not texts:
            return []

        return self._embed_texts_with_network_fallback(texts)

    def _embed_texts_with_network_fallback(self, texts: list[str]) -> list[list[float]]:
        last_error: httpx.HTTPError | None = None
        for attempt in range(self.network_retries):
            try:
                return self._embed_texts_once(texts)
            except httpx.HTTPError as exc:
                last_error = exc
                if len(texts) > 1:
                    # 大文档批量入库时，部分网关会直接断开批量请求；拆成单条可继续完成入库。
                    vectors: list[list[float]] = []
                    for text in texts:
                        vectors.extend(self._embed_texts_with_network_fallback([text]))
                    return vectors
                if attempt < self.network_retries - 1:
                    time.sleep(0.5 * (attempt + 1))

        assert last_error is not None
        raise EmbeddingProviderError(f"DashScope embedding request failed: {type(last_error).__name__}: {last_error}") from last_error

    def _embed_texts_once(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": {"texts": texts}, "parameters": {"dimension": self.dimensions}}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self._embedding_url(), headers=headers, json=payload)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text[:500] if exc.response is not None else str(exc)
                raise EmbeddingProviderError(f"DashScope embedding request failed: {detail}") from exc
            body = response.json()

        output = body.get("output") if isinstance(body, dict) else None
        data = output.get("embeddings") if isinstance(output, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingProviderError("DashScope embedding response shape is invalid")

        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list) or len(embedding) != self.dimensions:
                raise EmbeddingProviderError("DashScope embedding vector dimension is invalid")
            vectors.append([float(value) for value in embedding])
        return vectors

    def _embedding_url(self) -> str:
        if "/api/v1/services/embeddings/text-embedding/text-embedding" in self.base_url:
            return self.base_url
        return f"{self.base_url}/api/v1/services/embeddings/text-embedding/text-embedding"
