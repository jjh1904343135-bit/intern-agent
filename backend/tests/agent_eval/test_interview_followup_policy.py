from __future__ import annotations

import pytest

from app.agents.interview.evaluator import analyze_answer, select_followup_strategy
from app.agents.interview.models import CandidateProfile, JobProfile
from app.agents.interview.planner import build_question_plan
from app.agents.interview.runtime import build_summary, process_answer

from .eval_helpers import case_ids, load_jsonl


INTERVIEW_CASES = load_jsonl("interview_cases.jsonl")


@pytest.mark.parametrize("case", INTERVIEW_CASES, ids=case_ids(INTERVIEW_CASES))
def test_interview_followup_policy_matches_answer_quality(case: dict) -> None:
    plan = build_question_plan(
        job_profile=JobProfile(**case["job_profile"]),
        candidate_profile=CandidateProfile(**case["candidate_profile"]),
        round_type="mixed",
        difficulty=2,
    )
    planned_question = plan[0].to_dict()

    for followup_case in case["followup_cases"]:
        signals = analyze_answer(
            answer=followup_case["answer"],
            planned_question=planned_question,
            job_profile=case["job_profile"],
        )
        strategy = select_followup_strategy(answer_signals=signals, difficulty=4)
        if "expected_strategy" in followup_case:
            assert strategy == followup_case["expected_strategy"]
        else:
            assert strategy in set(followup_case["expected_strategy_in"])


@pytest.mark.parametrize("case", INTERVIEW_CASES, ids=case_ids(INTERVIEW_CASES))
def test_three_round_interview_story_keeps_evidence_chain(case: dict) -> None:
    plan = build_question_plan(
        job_profile=JobProfile(**case["job_profile"]),
        candidate_profile=CandidateProfile(**case["candidate_profile"]),
        round_type="mixed",
        difficulty=2,
    )
    state = {
        "session_id": "eval-session",
        "job_profile": case["job_profile"],
        "candidate_profile": case["candidate_profile"],
        "round_type": "mixed",
        "question_plan": [item.to_dict() for item in plan],
        "asked_questions": [],
        "evaluation_state": {},
        "difficulty": 2,
        "remaining_focus": case["job_profile"]["interview_focus"],
    }

    answers = [
        "我做过这个项目。",
        "我在 InternAgent 负责 RAG 检索链路，用 FastAPI 拆接口，用 Qdrant 存向量，并补了 pytest 回归测试。",
        "如果召回效果不稳定，我会先看 chunk、embedding、过滤条件和 Recall@k，再决定是否加 rerank 或缓存。",
    ]
    strategies: list[str] = []
    for index, answer in enumerate(answers, start=1):
        update = process_answer(agent_state=state, round_index=index, question_id=f"q-{index}", answer=answer)
        state = update["agent_state"]
        strategies.append(update["followup_strategy"])

    summary = build_summary(state)

    assert strategies[0] == "clarify"
    assert strategies[1] in {"challenge", "transfer"}
    assert state["difficulty"] >= 2
    assert len(state["asked_questions"]) == 3
    assert summary["evidence_chain"]
    assert summary["score_dimensions"]
    first_evidence = summary["evidence_chain"][0]
    assert {"question_id", "job_requirement", "resume_evidence", "answer_signal_summary", "followup_reason"}.issubset(first_evidence)
