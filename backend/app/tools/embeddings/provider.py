"""Embedding provider switch used by knowledge RAG."""

from __future__ import annotations

from app.core.settings import settings
from app.tools.embeddings.dashscope_adapter import DashScopeEmbeddingClient
from app.tools.embeddings.fastembed_adapter import embed_text as fastembed_text


def embed_texts(texts: list[str]) -> list[list[float]]:
    provider = settings.embedding_provider.lower().strip()
    if provider == "dashscope":
        client = DashScopeEmbeddingClient(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
        vectors: list[list[float]] = []
        for index in range(0, len(texts), 10):
            vectors.extend(client.embed_texts(texts[index : index + 10]))
        return vectors
    if provider == "fastembed":
        return [fastembed_text(text) for text in texts]
    raise ValueError(f"Unsupported EMBEDDING_PROVIDER={settings.embedding_provider}")


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]
