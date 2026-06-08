from __future__ import annotations

import pytest

from app.agents.supervisor import SupervisorAgent

from .eval_helpers import case_ids, load_jsonl


CHAT_CASES = load_jsonl("chat_cases.jsonl")


@pytest.mark.parametrize("case", CHAT_CASES, ids=case_ids(CHAT_CASES))
def test_chat_agent_classifies_golden_case_intent(case: dict) -> None:
    turn = SupervisorAgent().plan_turn(message=case["input"], history=[], tool_context={})

    assert turn.intent == case["expected_intent"]


@pytest.mark.parametrize("case", CHAT_CASES, ids=case_ids(CHAT_CASES))
def test_chat_agent_selects_expected_tools_for_intent(case: dict) -> None:
    turn = SupervisorAgent().plan_turn(message=case["input"], history=[], tool_context={})

    assert set(case["expected_tools"]).issubset(set(turn.tools))


def test_chat_agent_routes_natural_job_search_to_job_tool() -> None:
    turn = SupervisorAgent().plan_turn(message="帮我搜一下美团开发岗", history=[], tool_context={})

    assert turn.intent == "job_search"
    assert "job_search" in turn.tools
