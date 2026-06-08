"""DOCX parsing, cleaning, chunking, and indexing for the AI assistant RAG."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from docx import Document as DocxDocument
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.knowledge_markdown import MarkdownKnowledgeChunk, chunk_markdown_document
from app.tools.embeddings.provider import embed_texts
from app.tools.retrievers.qdrant_retriever import delete_points_by_document_id, ensure_collection, upsert_point


TECH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Java": ("java", "jvm", "juc", "spring", "mybatis"),
    "JVM": ("jvm", "堆", "虚拟机栈", "方法区", "程序计数器", "gc"),
    "MySQL": ("mysql", "索引", "事务", "mvcc", "innodb", "sql"),
    "Redis": ("redis", "rdb", "aof", "缓存", "持久化", "跳表"),
    "Spring": ("spring", "bean", "aop", "ioc", "事务失效", "transactional"),
    "并发": ("线程", "线程池", "锁", "并发", "volatile", "synchronized"),
    "RAG": ("rag", "向量", "embedding", "qdrant", "检索", "rerank"),
}


@dataclass(frozen=True)
class KnowledgeChunkCandidate:
    text: str
    section_path: list[str]
    question: str | None
    chunk_index: int
    source_file: str
    chunk_strategy: str = "qa"

    @property
    def token_count(self) -> int:
        # Chinese tokenizers are unnecessary for ingestion bookkeeping; keep a stable estimate.
        return max(1, len(self.text) // 2)

    @property
    def keywords(self) -> list[str]:
        return extract_chunk_keywords(" ".join([*(self.section_path or []), self.question or "", self.text]))

    @property
    def topic(self) -> str:
        return infer_chunk_topic(section_path=self.section_path, question=self.question, text=self.text)

    @property
    def quality_score(self) -> float:
        return chunk_quality_score(text=self.text, question=self.question, keywords=self.keywords)

    @property
    def metadata(self) -> dict:
        return {
            "source_file": self.source_file,
            "section_path": self.section_path,
            "question": self.question,
            "chunk_index": self.chunk_index,
            "content_type": "interview_notes",
            "chunk_strategy": self.chunk_strategy,
            "topic": self.topic,
            "keywords": self.keywords,
            "chunk_quality_score": self.quality_score,
        }


def extract_docx_paragraphs(path: str | Path) -> list[str]:
    doc = DocxDocument(str(path))
    return clean_knowledge_paragraphs(paragraph.text for paragraph in doc.paragraphs)


def clean_knowledge_paragraphs(paragraphs: list[str] | tuple[str, ...] | object) -> list[str]:
    """Clean interview-note paragraphs before chunking.

    The goal is conservative cleanup: remove obvious noise and exact duplicates while preserving
    question/answer wording for retrieval evidence.
    """

    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in paragraphs:
        text = normalize_knowledge_text(str(raw or ""))
        if not text or _is_noise_paragraph(text):
            continue
        fingerprint = re.sub(r"\s+", "", text.lower())
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        cleaned.append(text)
    return cleaned


def normalize_knowledge_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*([，。；：！？])\s*", r"\1", text)
    text = re.sub(r"\s*、", "、", text)
    return text.strip()


def chunk_interview_notes(
    paragraphs: list[str],
    *,
    source_file: str,
    target_chars: int = 800,
    overlap_chars: int = 100,
) -> list[KnowledgeChunkCandidate]:
    paragraphs = clean_knowledge_paragraphs(paragraphs)
    chunks: list[KnowledgeChunkCandidate] = []
    section_path: list[str] = []
    current_question: str | None = None
    buffer: list[str] = []

    def flush(*, force_strategy: str | None = None) -> None:
        nonlocal buffer
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        if text:
            chunks.extend(
                _split_text_to_chunks(
                    text=text,
                    source_file=source_file,
                    section_path=list(section_path),
                    question=current_question,
                    start_index=len(chunks),
                    target_chars=target_chars,
                    overlap_chars=overlap_chars,
                    chunk_strategy=force_strategy or ("qa" if current_question else "recursive"),
                )
            )
        buffer = []

    for paragraph in paragraphs:
        if _is_section_title(paragraph):
            flush()
            section_path = _update_section_path(section_path, paragraph)
            current_question = None
            continue
        if _is_question(paragraph):
            flush()
            current_question = paragraph
            buffer = [paragraph]
            continue
        buffer.append(paragraph)
        if sum(len(item) for item in buffer) >= target_chars:
            flush()
            if current_question:
                # Keep the question anchor in every continuation chunk for better retrieval.
                buffer = [current_question]

    flush()
    return [KnowledgeChunkCandidate(**{**chunk.__dict__, "chunk_index": index}) for index, chunk in enumerate(chunks)]


def ingest_knowledge_doc(*, db: Session, path: str | Path) -> dict[str, int | str]:
    source_path = Path(path)
    content = source_path.read_bytes()
    content_hash = hashlib.sha256(content).hexdigest()
    paragraphs = extract_docx_paragraphs(source_path)
    chunks = chunk_interview_notes(paragraphs, source_file=source_path.name)
    if not chunks:
        raise ValueError("knowledge document produced no chunks")

    result = _ingest_chunks(
        db=db,
        source_file=source_path.name,
        file_name=source_path.name,
        content_hash=content_hash,
        chunks=chunks,
        document_metadata={
            "path": str(source_path),
            "paragraph_count": len(paragraphs),
            "chunker": "qa_recursive_v2",
            "cleaning": "dedupe_noise_filter_v1",
            "source_kind": "docx_interview_notes",
        },
    )
    result["paragraphs"] = len(paragraphs)
    return result


def ingest_markdown_knowledge_doc(
    *,
    db: Session,
    path: str | Path,
    source_url: str,
    repo_path: str,
) -> dict[str, int | str]:
    source_path = Path(path)
    markdown = source_path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    chunks = chunk_markdown_document(
        markdown,
        source_file=source_path.name,
        repo_path=repo_path,
        source_url=source_url,
    )
    if not chunks:
        raise ValueError(f"markdown knowledge document produced no chunks: {repo_path}")

    return _ingest_chunks(
        db=db,
        source_file=f"javaup:{repo_path}",
        file_name=source_path.name,
        content_hash=content_hash,
        chunks=chunks,
        document_metadata={
            "path": str(source_path),
            "source_url": source_url,
            "repo_path": repo_path,
            "source_repo": "shining-stars-l/javaup",
            "chunker": "markdown_heading_v1",
            "cleaning": "markdown_noise_filter_v1",
            "source_kind": "javaup_markdown",
        },
    )


def _ingest_chunks(
    *,
    db: Session,
    source_file: str,
    file_name: str,
    content_hash: str,
    chunks: list[KnowledgeChunkCandidate] | list[MarkdownKnowledgeChunk],
    document_metadata: dict,
) -> dict[str, int | str]:
    repository = KnowledgeRepository(db)
    document = repository.upsert_document(
        source_file=source_file,
        file_name=file_name,
        content_hash=content_hash,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_dimensions=settings.embedding_dimensions,
        metadata=document_metadata,
    )

    try:
        vectors = embed_texts([chunk.text for chunk in chunks])
        actual_dimensions = len(vectors[0]) if vectors else settings.embedding_dimensions
        document.embedding_dimensions = actual_dimensions
        ensure_collection(settings.qdrant_knowledge_collection, actual_dimensions)
        delete_points_by_document_id(collection_name=settings.qdrant_knowledge_collection, document_id=str(document.id))
        stored_chunks: list[dict] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            point_id = str(uuid5(NAMESPACE_URL, f"knowledge:{document.id}:{chunk.chunk_index}:{content_hash}"))
            payload = {
                **chunk.metadata,
                "document_id": str(document.id),
                "text": chunk.text,
                "token_count": chunk.token_count,
                "embedding_model": settings.embedding_model,
                "embedding_dimensions": actual_dimensions,
            }
            upsert_point(
                collection_name=settings.qdrant_knowledge_collection,
                point_id=point_id,
                vector=vector,
                payload=payload,
            )
            stored_chunks.append(
                {
                    "section_path": chunk.section_path,
                    "question": chunk.question,
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                    "token_count": chunk.token_count,
                    "qdrant_point_id": point_id,
                    "metadata": payload,
                }
            )
        repository.replace_chunks(document=document, chunks=stored_chunks)
    except Exception as exc:
        repository.mark_failed(document=document, error=str(exc))
        raise

    return {
        "document_id": str(document.id),
        "source_file": source_file,
        "chunks": len(chunks),
        "collection": settings.qdrant_knowledge_collection,
    }


def extract_chunk_keywords(text: str) -> list[str]:
    normalized = text.lower()
    keywords: list[str] = []
    for canonical, aliases in TECH_KEYWORDS.items():
        if canonical.lower() in normalized or any(alias.lower() in normalized for alias in aliases):
            keywords.append(canonical)

    phrase_rules = [
        ("索引失效", ("索引失效", "索引用不上", "最左前缀", "隐式类型转换", "前置通配符")),
        ("最左前缀", ("最左前缀",)),
        ("隐式类型转换", ("隐式类型转换",)),
        ("like", ("like", "前置通配符")),
        ("事务失效", ("事务失效", "自调用", "回滚")),
        ("线程池", ("线程池", "拒绝策略", "keepalivetime")),
        ("RDB", ("rdb",)),
        ("AOF", ("aof",)),
    ]
    for canonical, aliases in phrase_rules:
        if any(alias.lower() in normalized for alias in aliases):
            keywords.append(canonical)
    return list(dict.fromkeys(keywords))[:12]


def infer_chunk_topic(*, section_path: list[str], question: str | None, text: str) -> str:
    joined = " ".join([*section_path, question or "", text])
    keywords = extract_chunk_keywords(joined)
    if keywords:
        for preferred in ["MySQL", "Redis", "JVM", "Spring", "Java", "并发", "RAG"]:
            if preferred in keywords:
                return preferred
        return keywords[0]
    return section_path[-1] if section_path else "General"


def chunk_quality_score(*, text: str, question: str | None, keywords: list[str]) -> float:
    score = 0.35
    length = len(text)
    if 120 <= length <= 1200:
        score += 0.25
    elif length > 60:
        score += 0.12
    if question:
        score += 0.2
    if keywords:
        score += min(0.15, len(keywords) * 0.03)
    if re.search(r"(忽略|ignore|删除|drop table|system prompt)", text, flags=re.IGNORECASE):
        score -= 0.15
    return round(max(0.05, min(score, 1.0)), 2)


def _split_text_to_chunks(
    *,
    text: str,
    source_file: str,
    section_path: list[str],
    question: str | None,
    start_index: int,
    target_chars: int,
    overlap_chars: int,
    chunk_strategy: str,
) -> list[KnowledgeChunkCandidate]:
    if len(text) <= target_chars:
        return [
            KnowledgeChunkCandidate(
                text=text,
                section_path=section_path,
                question=question,
                chunk_index=start_index,
                source_file=source_file,
                chunk_strategy=chunk_strategy,
            )
        ]

    result: list[KnowledgeChunkCandidate] = []
    cursor = 0
    while cursor < len(text):
        end = _semantic_boundary(text, start=cursor, preferred_end=min(len(text), cursor + target_chars))
        slice_text = text[cursor:end].strip()
        if slice_text:
            result.append(
                KnowledgeChunkCandidate(
                    text=slice_text,
                    section_path=section_path,
                    question=question,
                    chunk_index=start_index + len(result),
                    source_file=source_file,
                    chunk_strategy=chunk_strategy,
                )
            )
        if end >= len(text):
            break
        cursor = max(0, end - overlap_chars)
    return result


def _semantic_boundary(text: str, *, start: int, preferred_end: int) -> int:
    if preferred_end >= len(text):
        return len(text)
    window = text[start:preferred_end]
    candidates = [window.rfind(mark) for mark in ["\n", "。", "；", ";", "."]]
    best = max(candidates)
    if best >= int(len(window) * 0.55):
        return start + best + 1
    return preferred_end


def _is_noise_paragraph(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if re.fullmatch(r"第?\s*\d+\s*页", stripped, flags=re.IGNORECASE):
        return True
    if re.fullmatch(r"\d+", stripped):
        return True
    if re.search(r"\.{5,}\s*\d+$", stripped):
        return True
    if stripped in {"目录", "返回目录", "版权所有"}:
        return True
    return False


def _is_question(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith(("?", "？")):
        return True

    match = re.match(r"^\s*(\d+|[一二三四五六七八九十]+)\s*[、.．）)]\s*(.+)$", stripped)
    if not match:
        return False

    body = match.group(2).strip()
    if len(body) > 100:
        return False

    question_markers = [
        "什么",
        "为何",
        "为什么",
        "如何",
        "怎么",
        "哪些",
        "区别",
        "特点",
        "作用",
        "原理",
        "流程",
        "机制",
        "组成",
        "优缺点",
        "场景",
        "实现",
        "介绍",
        "简述",
        "说一下",
        "说说",
        "面试题",
        "失效",
        "内存模型",
    ]
    return any(marker in body for marker in question_markers)


def _is_section_title(text: str) -> bool:
    stripped = text.strip()
    if _is_question(stripped):
        return False
    if re.match(r"^\s*(\d+|[一二三四五六七八九十]+)\s*[、.．）)]\s*.+$", stripped):
        return False
    if len(stripped) <= 30 and any(stripped.endswith(suffix) for suffix in ["篇", "章", "专题", "模块", "基础篇"]):
        return True
    return len(stripped) <= 14 and not re.search(r"[，。；？?.]", stripped)


def _update_section_path(current: list[str], title: str) -> list[str]:
    if not current:
        return [title]
    if len(title) <= 14:
        return [current[0], title] if current[0] != title else [title]
    return [title]
