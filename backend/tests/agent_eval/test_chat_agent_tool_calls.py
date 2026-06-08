from __future__ import annotations

import pytest

from app.agents.supervisor import SupervisorAgent
from app.services.chat_service import ChatService

from .eval_helpers import assert_contains_terms, case_ids, load_jsonl


CHAT_CASES = load_jsonl("chat_cases.jsonl")


@pytest.mark.parametrize(
    "case",
    [case for case in CHAT_CASES if case.get("expected_tool_args", {}).get("job_search")],
    ids=case_ids([case for case in CHAT_CASES if case.get("expected_tool_args", {}).get("job_search")]),
)
def test_chat_agent_derives_job_search_arguments_from_user_input(case: dict) -> None:
    expected = case["expected_tool_args"]["job_search"]

    keyword = ChatService._keyword_from_message(case["input"])
    city = ChatService._city_from_message(case["input"])

    assert_contains_terms(keyword, expected["keyword_contains"])
    assert city == expected["city"]


@pytest.mark.parametrize("case", CHAT_CASES, ids=case_ids(CHAT_CASES))
def test_chat_agent_prompt_contains_output_contract_and_safety_guardrails(case: dict) -> None:
    turn = SupervisorAgent().plan_turn(message=case["input"], history=[], tool_context={})
    prompt_contract = f"{turn.system_prompt}\n{turn.prompt}"

    for required in case.get("must_include", []):
        assert required in prompt_contract

    assert "Never invent job postings" in turn.system_prompt
    assert "Never guarantee offers or admission" in turn.system_prompt
    assert "Never claim you submitted an application" in turn.system_prompt
