from __future__ import annotations

import re


def format_assistant_plain_text(text: str) -> str:
    """Convert model-style Markdown into readable plain Chinese chat text."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    in_code_block = False
    for raw_line in value.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block and _looks_like_debug_json(line):
            continue
        line = _clean_markdown_line(line)
        if line or (lines and lines[-1]):
            lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _clean_markdown_line(line: str) -> str:
    value = line.strip()
    value = re.sub(r"^#{1,6}\s*", "", value)
    value = re.sub(r"^>\s*", "", value)
    value = re.sub(r"^\s*[-*+]\s+", "", value)
    value = re.sub(r"^\s*\d+[.)]\s+", "", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    value = re.sub(r"__([^_]+)__", r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    return value.strip()


def _looks_like_debug_json(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("{") or stripped.startswith("[") or '"debug"' in stripped or "'debug'" in stripped
