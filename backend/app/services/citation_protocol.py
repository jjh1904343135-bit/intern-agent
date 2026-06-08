"""Structured citation protocol for RAG and assistant memories."""

from __future__ import annotations

import re
from typing import Any


CITATION_PROTOCOL_VERSION = "citation_v1"

_UNSAFE_TEXT_PATTERNS = (
    r"ignore\s+(?:all\s+)?(?:previous|system)[^.\n。;；]*(?:[.\n。;；]|$)",
    r"delete\s+resumes?[^.\n。;；]*(?:[.\n。;；]|$)",
    r"drop\s+table[^.\n。;；]*(?:[.\n。;；]|$)",
    r"忽略[^。\n；;]*(?:系统|之前|上面)[^。\n；;]*(?:[。\n；;]|$)",
    r"删除[^。\n；;]*(?:简历|数据库|用户)[^。\n；;]*(?:[。\n；;]|$)",
    r"覆盖[^。\n；;]*系统[^。\n；;]*(?:[。\n；;]|$)",
)

_SAFE_SOURCE_REF_KEYS = {
    "kind",
    "request_id",
    "agent_run_id",
    "message_id",
    "tool",
    "source",
    "source_kind",
    "result_count",
    "intent",
    "status",
}


def sanitize_reference_text(text: str) -> str:
    """Remove instruction-like text from retrieved references before metadata use."""
    sanitized = str(text or "")
    for pattern in _UNSAFE_TEXT_PATTERNS:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def normalize_knowledge_citations(citations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for citation in list(citations or []):
        source_file = str(citation.get("source_file") or "knowledge").strip() or "knowledge"
        chunk_index = citation.get("chunk_index")
        citation_id = f"knowledge:{source_file}:{chunk_index if chunk_index is not None else len(normalized) + 1}"
        normalized.append(
            {
                "citation_id": citation_id,
                "kind": "knowledge_chunk",
                "source_type": "knowledge_rag",
                "source_file": source_file,
                "section_path": [str(item) for item in citation.get("section_path") or []],
                "question": citation.get("question"),
                "chunk_index": chunk_index,
                "score": citation.get("score"),
                "source_url": citation.get("source_url"),
                "repo_path": citation.get("repo_path"),
            }
        )
    return normalized


def normalize_memory_citations(memory_items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(list(memory_items or []), 1):
        source_ref = _sanitize_source_ref(item.get("source_ref") or {})
        key = str(item.get("key") or f"memory-{index}")
        ref_id = source_ref.get("request_id") or source_ref.get("agent_run_id") or str(index)
        normalized.append(
            {
                "citation_id": f"memory:{key}:{ref_id}",
                "kind": "assistant_memory",
                "source_type": "assistant_memories",
                "key": key,
                "summary": sanitize_reference_text(str(item.get("summary") or ""))[:240],
                "source_ref": source_ref,
            }
        )
    return normalized


def build_citation_protocol(
    *,
    tool_context: dict[str, Any],
    memory_context: dict[str, Any] | None = None,
    memory_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    knowledge = tool_context.get("knowledge_search") or {}
    memory_items = list((memory_context or {}).get("items") or []) + list((memory_updates or {}).get("items") or [])
    hits = list(knowledge.get("hits") or [])
    sanitized_reference_samples = [
        sanitize_reference_text(str(hit.get("text") or ""))[:180]
        for hit in hits[:3]
        if sanitize_reference_text(str(hit.get("text") or ""))
    ]
    return {
        "version": CITATION_PROTOCOL_VERSION,
        "knowledge_citations": normalize_knowledge_citations(knowledge.get("citations") or []),
        "memory_citations": normalize_memory_citations(memory_items),
        "reference_safety": {
            "retrieved_context_is_untrusted": True,
            "prompt_injection_text_removed": any(str(hit.get("text") or "")[:180] != sample for hit, sample in zip(hits[:3], sanitized_reference_samples)),
        },
        "reference_samples": sanitized_reference_samples,
    }


def _sanitize_source_ref(source_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in dict(source_ref or {}).items()
        if key in _SAFE_SOURCE_REF_KEYS and isinstance(value, (str, int, float, bool)) and value is not None
    }
