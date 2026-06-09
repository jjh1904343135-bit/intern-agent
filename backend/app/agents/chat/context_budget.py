from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatContextBudget:
    context_window_tokens: int
    compression_ratio: float = 0.5
    reserved_output_tokens: int = 900
    keep_recent_messages: int = 6

    @property
    def threshold_tokens(self) -> int:
        return max(1, int(max(1, self.context_window_tokens) * self.compression_ratio))


def estimate_tokens(value: Any) -> int:
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    stripped = value.strip()
    if not stripped:
        return 0
    ascii_count = sum(1 for char in stripped if ord(char) < 128)
    non_ascii_count = len(stripped) - ascii_count
    return max(1, (ascii_count + 3) // 4 + non_ascii_count)


def maybe_compress_context(
    *,
    history: list[dict[str, Any]],
    file_memory_context: dict[str, Any],
    tool_context: dict[str, Any],
    prompt: str,
    budget: ChatContextBudget,
) -> dict[str, Any]:
    before_tokens = _context_tokens(
        history=history,
        file_memory_context=file_memory_context,
        tool_context=tool_context,
        prompt=prompt,
    )
    if before_tokens < budget.threshold_tokens:
        return {
            "triggered": False,
            "threshold_ratio": budget.compression_ratio,
            "threshold_tokens": budget.threshold_tokens,
            "before_tokens": before_tokens,
            "after_tokens": before_tokens,
            "history": history,
            "file_memory_context": file_memory_context,
            "summary": "",
        }

    recent_history = list(history[-budget.keep_recent_messages :])
    summary = _summarize_history(history[: max(0, len(history) - budget.keep_recent_messages)])
    compressed_file_memory = dict(file_memory_context)
    if summary:
        original_summary = str(compressed_file_memory.get("summary_text") or "")
        compressed_file_memory["summary_text"] = f"压缩历史摘要：{summary}\n近期长期记忆：{original_summary[:1200]}".strip()
    else:
        compressed_file_memory["summary_text"] = str(compressed_file_memory.get("summary_text") or "")[:1200]

    after_tokens = _context_tokens(
        history=recent_history,
        file_memory_context=compressed_file_memory,
        tool_context=tool_context,
        prompt=prompt,
    )
    return {
        "triggered": True,
        "threshold_ratio": budget.compression_ratio,
        "threshold_tokens": budget.threshold_tokens,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "history": recent_history,
        "file_memory_context": compressed_file_memory,
        "summary": summary,
    }


def context_compression_metadata(compression: dict[str, Any]) -> dict[str, Any]:
    return {
        "triggered": bool(compression.get("triggered")),
        "threshold_ratio": compression.get("threshold_ratio"),
        "threshold_tokens": compression.get("threshold_tokens"),
        "before_tokens": compression.get("before_tokens"),
        "after_tokens": compression.get("after_tokens"),
        "summary": compression.get("summary", ""),
    }


def _context_tokens(
    *,
    history: list[dict[str, Any]],
    file_memory_context: dict[str, Any],
    tool_context: dict[str, Any],
    prompt: str,
) -> int:
    return estimate_tokens(history) + estimate_tokens(file_memory_context.get("summary_text") or "") + estimate_tokens(tool_context) + estimate_tokens(prompt)


def _summarize_history(history: list[dict[str, Any]]) -> str:
    snippets: list[str] = []
    for item in history[-10:]:
        role = str(item.get("role") or "message")
        content = str(item.get("content") or "").replace("\n", " ").strip()
        if content:
            snippets.append(f"{role}: {content[:160]}")
    return "；".join(snippets)[:1600]
