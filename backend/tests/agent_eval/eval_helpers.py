from __future__ import annotations

import json
from pathlib import Path
from typing import Any


GOLDEN_CASES_DIR = Path(__file__).parent / "golden_cases"


def load_jsonl(file_name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    path = GOLDEN_CASES_DIR / file_name
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        cases.append(json.loads(stripped))
    return cases


def flatten_strings(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten_strings(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(flatten_strings(item) for item in value)
    return str(value)


def assert_contains_terms(text: str | None, terms: list[str]) -> None:
    haystack = (text or "").lower()
    missing = [term for term in terms if term.lower() not in haystack]
    assert not missing, f"missing expected terms {missing!r} in {text!r}"


def assert_excludes_terms(text: str | None, terms: list[str]) -> None:
    haystack = (text or "").lower()
    present = [term for term in terms if term.lower() in haystack]
    assert not present, f"forbidden terms {present!r} found in {text!r}"


def case_ids(cases: list[dict[str, Any]]) -> list[str]:
    return [str(case.get("id", index)) for index, case in enumerate(cases)]
