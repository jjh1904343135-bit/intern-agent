"""Repository for AI assistant knowledge documents and chunks."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from sqlalchemy import Select, delete, or_, select
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeChunk, KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_document_by_source_file(self, *, source_file: str) -> KnowledgeDocument | None:
        stmt: Select[tuple[KnowledgeDocument]] = select(KnowledgeDocument).where(KnowledgeDocument.source_file == source_file)
        return self.db.execute(stmt).scalar_one_or_none()

    def upsert_document(
        self,
        *,
        source_file: str,
        file_name: str,
        content_hash: str,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimensions: int,
        metadata: dict[str, Any],
    ) -> KnowledgeDocument:
        document = self.get_document_by_source_file(source_file=source_file)
        if document is None:
            document = KnowledgeDocument(
                source_file=source_file,
                file_name=file_name,
                content_hash=content_hash,
                parse_status="processing",
                chunk_count=0,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
                document_metadata=metadata,
            )
            self.db.add(document)
        else:
            document.file_name = file_name
            document.content_hash = content_hash
            document.parse_status = "processing"
            document.parse_error = None
            document.chunk_count = 0
            document.embedding_provider = embedding_provider
            document.embedding_model = embedding_model
            document.embedding_dimensions = embedding_dimensions
            document.document_metadata = metadata
            document.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(document)
        return document

    def replace_chunks(self, *, document: KnowledgeDocument, chunks: list[dict[str, Any]]) -> None:
        self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
        for chunk in chunks:
            self.db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    source_file=document.source_file,
                    section_path=chunk.get("section_path"),
                    question=chunk.get("question"),
                    chunk_index=chunk["chunk_index"],
                    text=chunk["text"],
                    token_count=chunk["token_count"],
                    qdrant_point_id=chunk["qdrant_point_id"],
                    chunk_metadata=chunk.get("metadata"),
                )
            )
        document.chunk_count = len(chunks)
        document.parse_status = "done"
        document.parse_error = None
        document.updated_at = datetime.utcnow()
        self.db.add(document)
        self.db.commit()

    def mark_failed(self, *, document: KnowledgeDocument, error: str) -> None:
        document.parse_status = "failed"
        document.parse_error = error
        document.updated_at = datetime.utcnow()
        self.db.add(document)
        self.db.commit()

    def search_chunks_lexical(self, *, query: str, limit: int = 20) -> list[KnowledgeChunk]:
        """BM25-style lexical retrieval used by Hybrid RAG.

        PostgreSQL full-text can be added later; this keeps retrieval portable while still using
        BM25 term-frequency and inverse-document-frequency signals instead of plain coverage.
        """

        tokens = _lexical_tokens(query)
        if not tokens:
            return []
        conditions = []
        for token in tokens[:8]:
            pattern = f"%{token}%"
            conditions.extend(
                [
                    KnowledgeChunk.text.ilike(pattern),
                    KnowledgeChunk.question.ilike(pattern),
                    KnowledgeChunk.source_file.ilike(pattern),
                ]
            )
        stmt = (
            select(KnowledgeChunk)
            .where(or_(*conditions))
            .order_by(KnowledgeChunk.created_at.desc())
            .limit(max(limit * 5, limit))
        )
        rows = list(self.db.execute(stmt).scalars().all())
        documents = [_chunk_searchable_text(chunk) for chunk in rows]
        raw_scores = bm25_scores(query_tokens=tokens, documents=documents)
        max_score = max(raw_scores or [0.0]) or 1.0
        for chunk, raw_score in zip(rows, raw_scores, strict=True):
            setattr(chunk, "_lexical_score", raw_score / max_score)
            setattr(chunk, "_bm25_raw_score", raw_score)
            setattr(chunk, "_retrieval_algorithm", "bm25")
        return sorted(rows, key=lambda chunk: getattr(chunk, "_bm25_raw_score", 0.0), reverse=True)[:limit]


def _lexical_tokens(query: str) -> list[str]:
    raw_tokens = re_split_query(query)
    stopwords = {"一下", "哪些", "为什么", "怎么", "如何", "常见", "情况", "面试", "讲", "说"}
    return [token for token in raw_tokens if token and token not in stopwords]


def re_split_query(query: str) -> list[str]:
    import re

    tokens = re.split(r"[\s,，。；;:：/、()（）]+", query)
    result: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if re.fullmatch(r"[A-Za-z0-9_+-]+", token):
            result.append(token)
            continue
        # Keep short Chinese technical terms intact; split only very long sentences.
        if len(token) <= 8:
            result.append(token)
        else:
            result.extend(item for item in re.findall(r"[A-Za-z0-9_+-]+|[\u4e00-\u9fff]{2,8}", token) if item)
    return list(dict.fromkeys(result))


def bm25_scores(*, query_tokens: list[str], documents: list[str], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Score documents with a compact BM25 variant.

    Chinese technical terms are matched as normalized substrings so phrases like `索引失效`
    or `零拷贝` still work without adding a heavy tokenizer.
    """

    normalized_tokens = [_normalize_token(token) for token in query_tokens if _normalize_token(token)]
    normalized_documents = [_normalize_token(document) for document in documents]
    if not normalized_tokens or not normalized_documents:
        return [0.0 for _ in documents]

    document_lengths = [max(len(re_split_query(document)), max(len(document) // 12, 1)) for document in documents]
    average_length = sum(document_lengths) / max(len(document_lengths), 1)
    document_count = len(documents)
    document_frequency = {
        token: sum(1 for document in normalized_documents if token in document)
        for token in normalized_tokens
    }

    scores: list[float] = []
    for document, document_length in zip(normalized_documents, document_lengths, strict=True):
        score = 0.0
        for token in normalized_tokens:
            frequency = document.count(token)
            if frequency <= 0:
                continue
            df = document_frequency.get(token, 0)
            idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1 - b + b * document_length / max(average_length, 1e-6))
            score += idf * (frequency * (k1 + 1)) / denominator
        scores.append(round(score, 6))
    return scores


def _chunk_searchable_text(chunk: KnowledgeChunk) -> str:
    metadata = chunk.chunk_metadata or {}
    return " ".join(
        [
            chunk.question or "",
            chunk.text or "",
            " ".join(str(item) for item in (chunk.section_path or [])),
            " ".join(str(item) for item in metadata.get("keywords") or []),
            str(metadata.get("topic") or ""),
            chunk.source_file or "",
        ]
    )


def _normalize_token(value: str) -> str:
    import re

    return re.sub(r"\s+", "", str(value or "").lower())
