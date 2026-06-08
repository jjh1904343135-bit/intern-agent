from __future__ import annotations

import hashlib
import re
from functools import lru_cache

from fastembed import TextEmbedding

from app.core.settings import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> TextEmbedding | None:
    # 模型实例做单例缓存，避免每次请求都重复初始化。
    try:
        return TextEmbedding(model_name=settings.fastembed_model, local_files_only=True)
    except Exception:
        return None


def _fallback_embed_text(text: str, size: int = 384) -> list[float]:
    values = [0.0] * size
    tokens = re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]+", text.lower())
    if not tokens:
        return values

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % size
        values[index] += 1.0

    norm = sum(item * item for item in values) ** 0.5 or 1.0
    return [item / norm for item in values]


def embed_text(text: str) -> list[float]:
    embedding_model = get_embedding_model()
    if embedding_model is not None:
        vector = next(embedding_model.embed([text]))
        return vector.tolist()

    # 离线环境无法下载 fastembed 模型时，退回到确定性向量，保证 Day 5 闭环可验证。
    return _fallback_embed_text(text)
