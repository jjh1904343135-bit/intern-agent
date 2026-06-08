from __future__ import annotations

import pytest

from app.services.resume_service import ResumeService

from .eval_helpers import assert_excludes_terms, case_ids, flatten_strings, load_jsonl


RESUME_SCORE_CASES = load_jsonl("resume_score_cases.jsonl")


@pytest.mark.parametrize("case", RESUME_SCORE_CASES, ids=case_ids(RESUME_SCORE_CASES))
def test_resume_score_report_follows_rubric_contract(case: dict) -> None:
    report = ResumeService._build_rule_score(case["parsed_content"])

    for field in case["required_report_fields"]:
        assert field in report
    for dimension in case["required_dimensions"]:
        matched = next((item for item in report["dimensions"] if item["dimension"] == dimension), None)
        assert matched is not None
        assert 0 <= matched["score"] <= 100
        assert 0 < matched["weight"] <= 1
        assert isinstance(matched["evidence"], list)
        assert isinstance(matched["problems"], list)
        assert isinstance(matched["suggestions"], list)
        assert 0 <= matched["confidence"] <= 1
    assert report["rubric_version"] == "resume_score_v1"
    assert report["rule_score"]["version"] == "resume_rule_v1"
    assert report["llm_review"]["status"] == "fallback"
    assert report["overall_score"] >= case["expected_min_score"]
    assert report["source"] == "fallback_rule"
    assert report["status"] == "fallback"
    assert_excludes_terms(flatten_strings(report), case["must_not_include"])
