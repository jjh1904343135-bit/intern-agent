from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.agents.chat.plan_schema import ALLOWED_CHAT_INTENTS, ALLOWED_CHAT_TOOLS, ChatPlan
from app.agents.chat.plan_validator import ChatPlanValidator
from app.agents.runtime import AgentContext, AgentResult, AgentRunner
from app.agents.supervisor import SupervisorAgent
from app.core.providers.base import LLMProvider
from app.core.settings import settings
from app.prompts import PromptRegistry
from app.utils.llm_json import LLMJsonError, extract_json_object


class ChatPlannerAgent:
    agent_name = "chat_planner"
    assistant_type = "ai_assistant"

    async def run(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AgentResult:
        content = await context.provider.generate(prompt, **kwargs)
        return AgentResult.from_context(context=context, agent_name=self.agent_name, content=content)

    async def stream(self, *, prompt: str, context: AgentContext, **kwargs: Any) -> AsyncIterator[str]:
        yield (await context.provider.generate(prompt, **kwargs))


class RuleBasedChatPlanner:
    def plan(
        self,
        *,
        message: str,
        history: list[dict] | None = None,
        source: str = "rule",
        issues: list[str] | None = None,
    ) -> ChatPlan:
        del history
        intent = SupervisorAgent._detect_intent(message)
        steps = SupervisorAgent._steps_for_intent(intent)
        tools = SupervisorAgent._tools_for_intent(intent)
        if SupervisorAgent._should_use_knowledge_search(message=message, intent=intent) and "knowledge_search" not in tools:
            tools.append("knowledge_search")
        return ChatPlan(
            intent=intent,
            steps=steps,
            tools=tools,
            confidence=1.0,
            source=source,
            issues=list(issues or []),
        )


class ChatPlannerService:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        enabled: bool = True,
        max_tokens: int | None = None,
        rule_planner: RuleBasedChatPlanner | None = None,
        validator: ChatPlanValidator | None = None,
    ) -> None:
        self.provider = provider
        self.enabled = enabled
        self.max_tokens = max_tokens or settings.chat_llm_planner_max_tokens
        self.rule_planner = rule_planner or RuleBasedChatPlanner()
        self.validator = validator or ChatPlanValidator()

    async def plan(self, *, message: str, history: list[dict] | None = None, request_id: str | None = None) -> ChatPlan:
        if not self.enabled or self.provider.name.lower() == "mock":
            return self.rule_planner.plan(message=message, history=history, source="rule")

        try:
            rendered = PromptRegistry().render(
                "chat/planner",
                {
                    "message": message,
                    "history_text": self._history_to_text(history or []),
                    "allowed_intents": sorted(ALLOWED_CHAT_INTENTS),
                    "allowed_tools": sorted(ALLOWED_CHAT_TOOLS),
                },
            )
            result = await AgentRunner().run(
                ChatPlannerAgent(),
                prompt=rendered.user,
                context=AgentContext(
                    provider=self.provider,
                    request_id=request_id or "chat-planner",
                    assistant_type="ai_assistant",
                ),
                system_prompt=rendered.system,
                temperature=0.0,
                max_tokens=self.max_tokens,
            )
            payload = extract_json_object(result.content)
        except LLMJsonError:
            return self.rule_planner.plan(
                message=message,
                history=history,
                source="rule_fallback",
                issues=["planner_parse_failed"],
            )
        except Exception as exc:
            return self.rule_planner.plan(
                message=message,
                history=history,
                source="rule_fallback",
                issues=[f"planner_unavailable:{exc.__class__.__name__}"],
            )

        validation = self.validator.validate(payload)
        if validation.fallback_required or validation.plan is None:
            return self.rule_planner.plan(
                message=message,
                history=history,
                source="rule_fallback",
                issues=validation.issues,
            )
        return validation.plan

    @staticmethod
    def _history_to_text(history: list[dict]) -> str:
        if not history:
            return "none"
        lines: list[str] = []
        for item in history[-6:]:
            role = str(item.get("role") or "unknown")
            content = str(item.get("content") or "").replace("\n", " ").strip()
            if content:
                lines.append(f"{role}: {content[:500]}")
        return "\n".join(lines) or "none"

