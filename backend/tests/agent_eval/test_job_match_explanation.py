from __future__ import annotations

import pytest

from app.tools.job_discovery import recommend_jobs

from .eval_helpers import assert_contains_terms, assert_excludes_terms, case_ids, flatten_strings, load_jsonl


JOB_MATCH_CASES = load_jsonl("job_match_cases.jsonl")


@pytest.mark.parametrize("case", JOB_MATCH_CASES, ids=case_ids(JOB_MATCH_CASES))
def test_job_recommendation_outputs_scores_explanation_and_priority(case: dict) -> None:
    recommended = recommend_jobs(
        case["jobs"],
        resume_profile=case["resume_profile"],
        city=case["input"].get("city"),
        experience=case["input"].get("experience"),
        skills=tuple(case["input"].get("skills") or ()),
    )
    top = recommended[0]

    assert top["canonical_title"] == case["expected_top_title"]
    for field in case["required_fields"]:
        assert field in top
    assert top["recommendation_score"] >= 0.7
    assert top["application_priority"] in {"high", "medium", "low"}
    assert isinstance(top["score_dimensions"], list)
    assert {item["dimension"] for item in top["score_dimensions"]}.issuperset({"技能匹配", "经验匹配", "城市匹配"})
    for dimension in top["score_dimensions"]:
        assert {"dimension", "score", "weight", "evidence", "problems", "suggestions", "confidence"}.issubset(dimension)
    assert top["evidence_summary"]["resume_evidence"]
    assert top["evidence_summary"]["job_requirement"]
    assert_contains_terms(flatten_strings(top), case["must_include"])
    assert_excludes_terms(flatten_strings(top), case["must_not_include"])
