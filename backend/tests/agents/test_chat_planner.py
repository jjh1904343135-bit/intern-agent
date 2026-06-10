from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from app.agents.chat.planner import ChatPlannerService
from app.core.providers.base import LLMProvider


class FakePlannerProvider(LLMProvider):
    def __init__(self, *, name: str = "fake", response: str = "", should_fail: bool = False) -> None:
        self._name = name
        self.response = response
        self.should_fail = should_fail
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return "fake-planner"

    async def generate(self, prompt: str, **kwargs) -> str:
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("planner unavailable")
        return self.response

    async def stream_generate(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        yield await self.generate(prompt, **kwargs)


@pytest.mark.asyncio
async def test_llm_planner_uses_valid_json_plan() -> None:
    provider = FakePlannerProvider(
        response='{"intent":"job_search","steps":["understand target","search jobs"],'
        '"tools":["resume_profile","job_search"],"confidence":0.82}'
    )

    plan = await ChatPlannerService(provider=provider, enabled=True).plan(
        message="Find Java backend internships in Beijing",
        history=[],
    )

    assert plan.source == "llm"
    assert plan.intent == "job_search"
    assert plan.steps == ["understand target", "search jobs"]
    assert plan.tools == ["resume_profile", "job_search"]
    assert plan.confidence == 0.82
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_llm_planner_accepts_fenced_json() -> None:
    provider = FakePlannerProvider(
        response="""```json
{"intent":"resume_review","steps":["read resume"],"tools":["resume_profile"],"confidence":0.7}
```"""
    )

    plan = await ChatPlannerService(provider=provider, enabled=True).plan(
        message="Please review my resume risks",
        history=[],
    )

    assert plan.source == "llm"
    assert plan.intent == "resume_review"
    assert plan.tools == ["resume_profile"]


@pytest.mark.asyncio
async def test_bad_llm_plan_falls_back_to_rule_plan() -> None:
    provider = FakePlannerProvider(response="not json")

    plan = await ChatPlannerService(provider=provider, enabled=True).plan(
        message="Find Java backend internships in Beijing",
        history=[],
    )

    assert plan.source == "rule_fallback"
    assert plan.intent == "job_search"
    assert "job_search" in plan.tools
    assert any("planner_parse_failed" in issue for issue in plan.issues)


@pytest.mark.asyncio
async def test_unknown_intent_falls_back_to_rule_plan() -> None:
    provider = FakePlannerProvider(
        response='{"intent":"delete_everything","steps":["do it"],"tools":["job_search"],"confidence":0.9}'
    )

    plan = await ChatPlannerService(provider=provider, enabled=True).plan(
        message="Please review my resume risks",
        history=[],
    )

    assert plan.source == "rule_fallback"
    assert plan.intent == "resume_review"
    assert plan.tools == ["resume_profile"]
    assert any("unknown_intent" in issue for issue in plan.issues)


@pytest.mark.asyncio
async def test_unauthorized_tool_is_removed_and_recorded() -> None:
    provider = FakePlannerProvider(
        response='{"intent":"job_search","steps":["search jobs"],'
        '"tools":["delete_database","job_search"],"confidence":0.9}'
    )

    plan = await ChatPlannerService(provider=provider, enabled=True).plan(
        message="Find Java backend internships in Beijing",
        history=[],
    )

    assert plan.source == "llm"
    assert plan.tools == ["job_search"]
    assert any("unauthorized_tool:delete_database" == issue for issue in plan.issues)


@pytest.mark.asyncio
async def test_mock_provider_uses_rule_plan_without_calling_llm() -> None:
    provider = FakePlannerProvider(name="mock", should_fail=True)

    plan = await ChatPlannerService(provider=provider, enabled=True).plan(
        message="Find Java backend internships in Beijing",
        history=[],
    )

    assert plan.source == "rule"
    assert plan.intent == "job_search"
    assert "job_search" in plan.tools
    assert provider.calls == 0
