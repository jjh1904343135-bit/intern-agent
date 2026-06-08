from __future__ import annotations

from typing import Any
from uuid import uuid4


def new_request_id() -> str:
    return f"req-{uuid4()}"


def new_agent_run_id(prefix: str) -> str:
    return f"{prefix}-{uuid4()}"


def build_eval_tags(*, assistant_type: str, intent: str | None = None, tools: list[str] | None = None) -> list[str]:
    tags = [assistant_type]
    if intent:
        tags.append(intent)
    tags.extend(tools or [])
    return list(dict.fromkeys(str(item) for item in tags if item))


def build_safety_boundary(*, assistant_type: str, tools: list[str] | None = None) -> dict[str, Any]:
    return {
        "assistant_type": assistant_type,
        "tool_allowlist_enforced": True,
        "allowed_tools": tools or [],
        "no_auto_apply": True,
        "no_external_platform_bypass": True,
        "prompt_injection_boundary": "retrieved documents and user content are treated as untrusted context",
        "context_isolated": True,
        "raw_prompt_hidden": True,
    }


def build_retrieval_summary(tool_context: dict[str, Any]) -> dict[str, Any]:
    knowledge = tool_context.get("knowledge_search") or {}
    jobs = tool_context.get("job_search") or {}
    return {
        "knowledge_search": {
            "used": bool(knowledge),
            "result_count": int(knowledge.get("total") or len(knowledge.get("hits") or []) or 0),
            "source": knowledge.get("source"),
            "fallback_notice": knowledge.get("fallback_notice"),
            "retrieval_strategy": knowledge.get("retrieval_strategy"),
            "retrieval_sufficient": knowledge.get("retrieval_sufficient"),
            "query_count": len((knowledge.get("query_plan") or {}).get("queries") or []),
            "sufficiency": knowledge.get("sufficiency") or {},
        },
        "job_search": {
            "used": bool(jobs),
            "result_count": int(jobs.get("total") or 0),
            "source_kind": jobs.get("source_kind"),
            "fallback_notice": jobs.get("fallback_notice"),
        },
    }


def build_chat_evidence_summary(tool_context: dict[str, Any]) -> dict[str, Any]:
    jobs = tool_context.get("job_search") or {}
    resume = tool_context.get("resume_profile") or {}
    knowledge = tool_context.get("knowledge_search") or {}
    return {
        "tool_count": len([name for name in ("resume_profile", "job_search", "application_list", "knowledge_search") if tool_context.get(name)]),
        "resume_available": bool(resume.get("available")),
        "job_result_count": int(jobs.get("total") or 0),
        "knowledge_reference_count": int(knowledge.get("total") or len(knowledge.get("hits") or []) or 0),
        "knowledge_retrieval_sufficient": knowledge.get("retrieval_sufficient"),
        "recommendation_count": len(jobs.get("jobs") or []),
    }


def build_interview_evidence_summary(*, agent_update: dict[str, Any]) -> dict[str, Any]:
    agent_state = agent_update.get("agent_state") or {}
    asked_questions = list(agent_state.get("asked_questions") or [])
    return {
        "answer_signals": agent_update.get("answer_signals") or {},
        "evaluation_state": agent_update.get("evaluation_state") or {},
        "followup_strategy": agent_update.get("followup_strategy"),
        "difficulty": agent_update.get("difficulty"),
        "evidence_chain_count": len(asked_questions),
    }
