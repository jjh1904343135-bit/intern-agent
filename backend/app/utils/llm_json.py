from __future__ import annotations

import json
import re
from typing import Any


class LLMJsonError(Exception):
    pass


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if not text:
        raise LLMJsonError("LLM response is empty")

    candidates = [text]
    fenced = _JSON_BLOCK_RE.findall(text)
    candidates.extend(fenced)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    raise LLMJsonError(f"Unable to extract JSON object from: {raw_text}")
