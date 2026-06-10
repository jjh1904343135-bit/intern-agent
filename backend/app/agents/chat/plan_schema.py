from __future__ import annotations

from dataclasses import dataclass, field


ALLOWED_CHAT_INTENTS = {
    "job_search",
    "resume_review",
    "interview_practice",
    "application_tracking",
    "career_coaching",
}

ALLOWED_CHAT_TOOLS = {
    "resume_profile",
    "job_search",
    "application_list",
    "knowledge_search",
}


@dataclass(frozen=True)
class ChatPlan:
    intent: str
    steps: list[str]
    tools: list[str]
    confidence: float = 1.0
    source: str = "rule"
    issues: list[str] = field(default_factory=list)

