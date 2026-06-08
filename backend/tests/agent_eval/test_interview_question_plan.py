from __future__ import annotations

import pytest

from app.agents.interview.models import CandidateProfile, JobProfile
from app.agents.interview.planner import build_question_plan

from .eval_helpers import assert_contains_terms, assert_excludes_terms, case_ids, flatten_strings, load_jsonl


INTERVIEW_CASES = load_jsonl("interview_cases.jsonl")


@pytest.mark.parametrize("case", INTERVIEW_CASES, ids=case_ids(INTERVIEW_CASES))
def test_interview_question_plan_covers_job_resume_intersection(case: dict) -> None:
    plan = build_question_plan(
        job_profile=JobProfile(**case["job_profile"]),
        candidate_profile=CandidateProfile(**case["candidate_profile"]),
        round_type="mixed",
        difficulty=2,
    )
    plan_text = flatten_strings([question.to_dict() for question in plan])
    categories = {question.category for question in plan}

    assert {"experience", "technical", "system_design"}.issubset(categories)
    assert_contains_terms(plan_text, case["expected_question_focus"])
    assert_excludes_terms(plan_text, case["must_not_focus"])
