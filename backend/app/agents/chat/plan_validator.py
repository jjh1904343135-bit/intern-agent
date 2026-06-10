from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.chat.plan_schema import ALLOWED_CHAT_INTENTS, ALLOWED_CHAT_TOOLS, ChatPlan
from app.agents.supervisor import SupervisorAgent


@dataclass(frozen=True)
class ChatPlanValidation:
    plan: ChatPlan | None
    issues: list[str]
    fallback_required: bool = False


class ChatPlanValidator:
    allowed_intents = ALLOWED_CHAT_INTENTS
    allowed_tools = ALLOWED_CHAT_TOOLS

    def validate(self, payload: dict[str, Any]) -> ChatPlanValidation:
        issues: list[str] = []
        intent = str(payload.get("intent") or "").strip()
        if intent not in self.allowed_intents:
            issues.append(f"unknown_intent:{intent or 'empty'}")
            return ChatPlanValidation(plan=None, issues=issues, fallback_required=True)

        steps = self._clean_string_list(payload.get("steps"))
        if not steps:
            steps = SupervisorAgent._steps_for_intent(intent)
            issues.append("empty_steps_defaulted")

        raw_tools = self._clean_string_list(payload.get("tools"))
        tools: list[str] = []
        seen: set[str] = set()
        for tool in raw_tools:
            if tool in seen:
                issues.append(f"duplicate_tool:{tool}")
                continue
            seen.add(tool)
            if tool not in self.allowed_tools:
                issues.append(f"unauthorized_tool:{tool}")
                continue
            tools.append(tool)

        if not tools:
            tools = SupervisorAgent._tools_for_intent(intent)
            issues.append("empty_tools_defaulted")

        confidence = self._confidence(payload.get("confidence"))
        return ChatPlanValidation(
            plan=ChatPlan(
                intent=intent,
                steps=steps,
                tools=tools,
                confidence=confidence,
                source="llm",
                issues=issues,
            ),
            issues=issues,
            fallback_required=False,
        )

    @staticmethod
    def _clean_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, confidence))

