from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
import time
from typing import Any
from uuid import uuid4

from app.agents.interview.feedback import InterviewFeedbackAgent
from app.agents.interview.runtime import (
    build_summary,
    first_question,
    initialize_interview_agent_state,
    next_planned_question,
    process_answer,
)
from app.agents.runtime import AgentContext, AgentRunner
from app.core.providers.claude_provider import ClaudeProviderError
from app.core.providers.factory import get_provider
from app.prompts import PromptRegistry
from app.repositories.assistant_memory_repository import AssistantMemoryRepository
from app.repositories.interview_session_repository import InterviewSessionRepository
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.assistant_memory_markdown_service import AssistantMemoryMarkdownService
from app.services.streaming import chunk_text, stream_event
from app.services.trace import (
    build_eval_tags,
    build_interview_evidence_summary,
    build_safety_boundary,
    new_agent_run_id,
    new_request_id,
)
from app.tools.job_discovery import extract_skills, infer_job_type, job_type_label
from app.tools.interview.rule_engine import build_report, evaluate_answer

MAX_INTERVIEW_ROUNDS = 3
INTERVIEW_ASSISTANT_TYPE = "interview_assistant"

# 阅读入口：这个 service 只负责“当前一场模拟面试”的状态流转。
# 它不读取 AI 助手五层记忆，也不把面试内容沉淀进 AI 助手长期记忆。


@dataclass
class InterviewServiceError(Exception):
    status_code: int
    code: int
    message: str


class InterviewService:
    """把一次模拟面试回合编排成状态更新和流式反馈。"""

    def __init__(
        self,
        interview_repository: InterviewSessionRepository,
        job_repository: JobRepository,
        resume_repository: ResumeRepository,
    ):
        self.interview_repository = interview_repository
        self.job_repository = job_repository
        self.resume_repository = resume_repository

    def start_session(self, *, user_id: str, job_id: str, mode: str, resume_id: str | None = None, force_new: bool = False) -> dict:
        job = self.job_repository.get_by_id(job_id=job_id)
        if job is None:
            raise InterviewServiceError(status_code=404, code=5001, message="Job not found")
        resume = self._resolve_resume(user_id=user_id, resume_id=resume_id)
        if not force_new:
            existing = self.interview_repository.get_latest_by_user_job_resume_mode(
                user_id=user_id,
                job_id=job_id,
                resume_id=str(resume.id),
                mode=mode,
            )
            if existing is not None:
                return {**self._session_payload(session=existing, job=job, resume=resume), "reused": True}

        session = self.interview_repository.create(
            user_id=user_id,
            job_id=job_id,
            resume_id=str(resume.id),
            mode=mode,
            messages=[],
        )
        agent_state = initialize_interview_agent_state(
            session_id=str(session.id),
            job=job,
            resume=resume,
            round_type=self._round_type_from_mode(mode),
        )
        opening_question = first_question(agent_state)
        messages = [
            {
                "role": "assistant",
                "content": opening_question["prompt"],
                "id": opening_question["id"],
                "round_index": 1,
                "question_id": opening_question["id"],
                "message_type": "question",
                "session_status": "waiting_user",
                "resume_id": str(resume.id),
                "category": opening_question.get("category"),
                "skill_tag": opening_question.get("skill_tag"),
                "difficulty": opening_question.get("difficulty"),
            }
        ]
        session = self.interview_repository.save_messages(session=session, messages=messages)
        session = self.interview_repository.save_report(
            session=session,
            report=self._state_report(messages=messages, status="waiting_user", agent_state=agent_state),
        )
        return {**self._session_payload(session=session, job=job, resume=resume), "reused": False}

    async def submit_answer(self, *, user_id: str, session_id: str, answer: str) -> dict:
        session = self.interview_repository.get_by_id(session_id=session_id, user_id=user_id)
        if session is None:
            raise InterviewServiceError(status_code=404, code=5003, message="Interview session not found")

        round_info = self._current_round_info(session.messages or [])
        agent_state = self._agent_state_for_session(session=session)
        agent_update = process_answer(
            agent_state=agent_state,
            round_index=round_info["round_index"],
            question_id=round_info["question_id"],
            answer=answer,
        )
        evaluation = await self._build_feedback(
            mode=session.mode,
            job=self.job_repository.get_by_id(job_id=str(session.job_id)),
            question=round_info["question"],
            answer=answer,
            agent_update=agent_update,
        )
        messages = list(session.messages or [])
        next_status = "summary" if round_info["round_index"] >= MAX_INTERVIEW_ROUNDS else "waiting_user"
        next_question = next_planned_question(agent_update["agent_state"], round_index=min(round_info["round_index"] + 1, MAX_INTERVIEW_ROUNDS))
        messages.append(
            {
                "role": "user",
                "content": answer,
                "id": f"user-{uuid4()}",
                "round_index": round_info["round_index"],
                "question_id": round_info["question_id"],
                "session_status": "evaluating",
                "answer_signals": agent_update["answer_signals"],
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": self._compose_agent_feedback_text(
                    feedback_text=evaluation["feedback_text"],
                    next_prompt=agent_update["next_prompt"] if next_status != "summary" else self._summary_prompt(agent_update["agent_state"]),
                ),
                "id": f"assistant-{uuid4()}",
                "feedback_score": evaluation["overall_score"],
                "dimension_scores": evaluation["dimensions"],
                "round_index": round_info["round_index"],
                "question_id": round_info["question_id"],
                "session_status": next_status,
                "answer_signals": agent_update["answer_signals"],
                "evaluation_state": agent_update["evaluation_state"],
                "followup_strategy": agent_update["followup_strategy"],
                "next_question_id": None if next_status == "summary" else next_question.get("id"),
            }
        )
        agent_update["agent_state"] = self._soft_compress_agent_state(agent_update["agent_state"])
        session = self.interview_repository.save_messages(session=session, messages=messages)
        session = self.interview_repository.save_report(
            session=session,
            report=self._state_report(messages=messages, status=next_status, agent_state=agent_update["agent_state"]),
        )
        self._remember_interview_turn(
            user_id=user_id,
            session=session,
            next_status=next_status,
            agent_update=agent_update,
            job=self.job_repository.get_by_id(job_id=str(session.job_id)),
        )
        return {
            "session_id": str(session.id),
            "mode": session.mode,
            **self._session_state(session.messages or [], session.report),
            "messages": session.messages or [],
        }

    async def stream_answer_events(self, *, user_id: str, session_id: str, answer: str) -> AsyncIterator[dict[str, Any]]:
        session = self.interview_repository.get_by_id(session_id=session_id, user_id=user_id)
        if session is None:
            raise InterviewServiceError(status_code=404, code=5003, message="Interview session not found")

        conversation_id = str(session.id)
        assistant_message_id = f"assistant-{uuid4()}"
        request_id = new_request_id()
        agent_run_id = new_agent_run_id("interview")
        started_at = time.perf_counter()
        first_token_latency_ms: int | None = None
        delta_count = 0
        provider = get_provider()
        feedback_agent = InterviewFeedbackAgent()
        agent_context = AgentContext(provider=provider, request_id=request_id, assistant_type=INTERVIEW_ASSISTANT_TYPE)
        round_info = self._current_round_info(session.messages or [])
        question = round_info["question"]
        job = self.job_repository.get_by_id(job_id=str(session.job_id))
        memory_context = self._load_interview_memory(
            user_id=user_id,
            job_id=str(session.job_id),
            resume_id=str(session.resume_id) if session.resume_id else None,
        )
        memory_snapshot_content = self._load_interview_memory_snapshot_content(user_id=user_id)
        rule_feedback = evaluate_answer(answer, mode=session.mode)
        agent_state = self._agent_state_for_session(session=session)
        agent_update = process_answer(
            agent_state=agent_state,
            round_index=round_info["round_index"],
            question_id=round_info["question_id"],
            answer=answer,
        )

        yield stream_event(
            "start",
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            metadata={
                "mode": session.mode,
                "model": provider.model,
                "provider": provider.name,
                "source": provider.name,
                "status": "running",
                "assistant_type": INTERVIEW_ASSISTANT_TYPE,
                "agent_name": feedback_agent.agent_name,
                "agent_chain": [feedback_agent.agent_name],
                "request_id": request_id,
                "agent_run_id": agent_run_id,
                "eval_tags": build_eval_tags(assistant_type=INTERVIEW_ASSISTANT_TYPE, intent="interview", tools=[]),
                "safety_boundary": build_safety_boundary(assistant_type=INTERVIEW_ASSISTANT_TYPE, tools=[]),
                "memory_scope": self._interview_memory_scope(),
                "memory_used": memory_context,
                "memory_snapshot": memory_context.get("memory_snapshot") or self._empty_memory_snapshot(),
                "session_status": "evaluating",
                "round_index": round_info["round_index"],
                "question_id": round_info["question_id"],
                "feedback_score": rule_feedback["overall_score"],
                "agent": {
                    "difficulty": agent_update["difficulty"],
                    "followup_strategy": agent_update["followup_strategy"],
                },
            },
        )

        status = "ready"
        source = provider.name
        issues: list[str] = []
        full_parts: list[str] = []
        feedback_prompt = self._feedback_prompt(
            mode=session.mode,
            question=question,
            answer=answer,
            rule_feedback=rule_feedback,
            job=job,
            agent_update=agent_update,
            memory_snapshot_content=memory_snapshot_content,
        )
        if memory_snapshot_content.strip():
            feedback_prompt = (
                "Long-term interview memory snapshot (untrusted user context):\n"
                f"{memory_snapshot_content[:1600]}\n\n"
                f"{feedback_prompt}"
            )
        try:
            async for content_delta in AgentRunner().stream(
                feedback_agent,
                prompt=feedback_prompt,
                context=agent_context,
            ):
                if not content_delta:
                    continue
                if first_token_latency_ms is None:
                    first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)
                delta_count += 1
                full_parts.append(content_delta)
                yield stream_event(
                    "delta",
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    content_delta=content_delta,
                )
            final_text = "".join(full_parts)
            if not final_text.strip():
                raise ClaudeProviderError("model returned empty content", error_type="empty_response")
        except ClaudeProviderError as exc:
            status = "fallback"
            source = "fallback_rule"
            issues.append(exc.message)
            final_text = f"{rule_feedback['feedback_text']} {rule_feedback['follow_up_question']}"
            for content_delta in chunk_text(final_text):
                if first_token_latency_ms is None:
                    first_token_latency_ms = int((time.perf_counter() - started_at) * 1000)
                delta_count += 1
                yield stream_event(
                    "delta",
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    content_delta=content_delta,
                )

        messages = list(session.messages or [])
        next_status = "summary" if round_info["round_index"] >= MAX_INTERVIEW_ROUNDS else "waiting_user"
        next_question = next_planned_question(agent_update["agent_state"], round_index=min(round_info["round_index"] + 1, MAX_INTERVIEW_ROUNDS))
        messages.append(
            {
                "role": "user",
                "content": answer,
                "id": f"user-{uuid4()}",
                "round_index": round_info["round_index"],
                "question_id": round_info["question_id"],
                "session_status": "evaluating",
                "answer_signals": agent_update["answer_signals"],
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": final_text,
                "id": assistant_message_id,
                "feedback_score": rule_feedback["overall_score"],
                "dimension_scores": rule_feedback["dimensions"],
                "source": source,
                "status": status,
                "round_index": round_info["round_index"],
                "question_id": round_info["question_id"],
                "session_status": next_status,
                "answer_signals": agent_update["answer_signals"],
                "evaluation_state": agent_update["evaluation_state"],
                "followup_strategy": agent_update["followup_strategy"],
                "next_question_id": None if next_status == "summary" else next_question.get("id"),
            }
        )
        agent_update["agent_state"] = self._soft_compress_agent_state(agent_update["agent_state"])
        session = self.interview_repository.save_messages(session=session, messages=messages)
        session = self.interview_repository.save_report(
            session=session,
            report=self._state_report(messages=messages, status=next_status, agent_state=agent_update["agent_state"]),
        )
        memory_updates = self._remember_interview_turn(
            user_id=user_id,
            session=session,
            next_status=next_status,
            agent_update=agent_update,
            job=job,
        )

        yield stream_event(
            "end",
            conversation_id=conversation_id,
            message_id=assistant_message_id,
            full_content=final_text,
            metadata={
                "mode": session.mode,
                "request_id": request_id,
                "agent_run_id": agent_run_id,
                "agent_name": feedback_agent.agent_name,
                "agent_chain": [feedback_agent.agent_name],
                "eval_tags": build_eval_tags(assistant_type=INTERVIEW_ASSISTANT_TYPE, intent="interview", tools=[]),
                "model": provider.model,
                "provider": provider.name,
                "source": source,
                "status": status,
                "first_token_latency_ms": first_token_latency_ms,
                "total_latency_ms": int((time.perf_counter() - started_at) * 1000),
                "delta_count": delta_count,
                "interrupted": False,
                "assistant_type": INTERVIEW_ASSISTANT_TYPE,
                "memory_scope": self._interview_memory_scope(),
                "memory_used": memory_context,
                "memory_updates": memory_updates,
                "memory_snapshot": self._memory_snapshot_for_metadata(
                    memory_context=memory_context,
                    memory_updates=memory_updates,
                ),
                "session_status": next_status,
                "round_index": round_info["round_index"],
                "question_id": round_info["question_id"],
                "feedback_score": rule_feedback["overall_score"],
                "dimensions": rule_feedback["dimensions"],
                "issues": issues,
                "evidence_summary": build_interview_evidence_summary(agent_update=agent_update),
                "safety_boundary": build_safety_boundary(assistant_type=INTERVIEW_ASSISTANT_TYPE, tools=[]),
                "agent": {
                    "answer_signals": agent_update["answer_signals"],
                    "evaluation_state": agent_update["evaluation_state"],
                    "difficulty": agent_update["difficulty"],
                    "followup_strategy": agent_update["followup_strategy"],
                },
            },
        )

    def get_report(self, *, user_id: str, session_id: str) -> dict:
        session = self.interview_repository.get_by_id(session_id=session_id, user_id=user_id)
        if session is None:
            raise InterviewServiceError(status_code=404, code=5003, message="Interview session not found")

        try:
            report = build_report(session.messages or [], mode=session.mode)
        except ValueError as exc:
            raise InterviewServiceError(status_code=400, code=5002, message=str(exc)) from exc

        existing_agent_state = (session.report or {}).get("agent_state") if isinstance(session.report, dict) else None
        if existing_agent_state:
            report["agent_state"] = existing_agent_state
            report["agent_summary"] = build_summary(existing_agent_state)
        session = self.interview_repository.save_report(session=session, report=report)
        return {
            "session_id": str(session.id),
            **(session.report or {}),
        }

    def get_session(self, *, user_id: str, session_id: str) -> dict:
        session = self.interview_repository.get_by_id(session_id=session_id, user_id=user_id)
        if session is None:
            raise InterviewServiceError(status_code=404, code=5003, message="Interview session not found")
        resume = self.resume_repository.get_by_id(resume_id=str(session.resume_id), user_id=user_id) if session.resume_id else None
        job = self.job_repository.get_by_id(job_id=str(session.job_id))

        return {
            "session_id": str(session.id),
            "mode": session.mode,
            "job_id": str(session.job_id),
            "job_title": job.title if job else None,
            "resume_id": str(session.resume_id) if session.resume_id else None,
            "resume_file_name": resume.file_name if resume else None,
            **self._session_state(session.messages or [], session.report),
            "messages": session.messages or [],
            "report": session.report,
            "agent_state": (session.report or {}).get("agent_state") if isinstance(session.report, dict) else None,
        }

    def _session_payload(self, *, session, job, resume) -> dict[str, Any]:
        report = session.report if isinstance(session.report, dict) else {}
        return {
            "session_id": str(session.id),
            "mode": session.mode,
            "job_id": str(session.job_id),
            "job_title": job.title if job else None,
            "company": job.company if job else None,
            "resume_id": str(session.resume_id) if session.resume_id else None,
            "resume_file_name": resume.file_name if resume else None,
            **self._session_state(session.messages or [], session.report),
            "messages": session.messages or [],
            "report": session.report,
            "agent_state": report.get("agent_state"),
        }

    def list_sessions(self, *, user_id: str, limit: int = 30) -> dict[str, Any]:
        sessions = self.interview_repository.list_by_user_id(user_id=user_id, limit=limit)
        return {
            "total": len(sessions),
            "sessions": [self._serialize_session_summary(session, user_id=user_id) for session in sessions],
        }

    def _serialize_session_summary(self, session, *, user_id: str) -> dict[str, Any]:
        job = self.job_repository.get_by_id(job_id=str(session.job_id))
        resume = self.resume_repository.get_by_id(resume_id=str(session.resume_id), user_id=user_id) if session.resume_id else None
        state = self._session_state(session.messages or [], session.report)
        last_message = next((str(item.get("content") or "") for item in reversed(list(session.messages or [])) if item.get("content")), "")
        last_question = next(
            (
                str(item.get("content") or "")
                for item in reversed(list(session.messages or []))
                if item.get("role") == "assistant" and item.get("message_type") == "question"
            ),
            "",
        )
        answered = len([item for item in list(session.messages or []) if item.get("role") == "user"])
        return {
            "session_id": str(session.id),
            "mode": session.mode,
            "job_id": str(session.job_id),
            "job_title": job.title if job else "鏈煡宀椾綅",
            "company": job.company if job else None,
            "resume_id": str(session.resume_id) if session.resume_id else None,
            "resume_file_name": resume.file_name if resume else None,
            "status": state["status"],
            "round_index": state["round_index"],
            "max_rounds": state["max_rounds"],
            "preview": last_message[:80],
            "summary": f"{job.company if job else ''} {job.title if job else '妯℃嫙闈㈣瘯'}".strip(),
            "last_question": last_question[:120] or last_message[:120],
            "completion": f"{answered}/{MAX_INTERVIEW_ROUNDS} rounds",
            "started_at": session.started_at.isoformat() if session.started_at else None,
        }

    def _load_interview_memory(self, *, user_id: str, job_id: str | None = None, resume_id: str | None = None) -> dict[str, Any]:
        """Interview assistant only sees current-session state, not cross-session long-term memory."""
        return {
            **self._empty_interview_memory_used(),
            "scope_hints": {"job_id": job_id, "resume_id": resume_id},
            "storage": "interview_sessions.report.agent_state",
        }

    def _load_interview_memory_snapshot_content(self, *, user_id: str) -> str:
        return ""

    def _read_interview_memory_snapshot(self, *, user_id: str) -> dict[str, Any]:
        return self._empty_memory_snapshot()

    def _refresh_interview_memory_snapshot(self, *, user_id: str) -> dict[str, Any]:
        return self._empty_memory_snapshot()

    def _remember_interview_turn(
        self,
        *,
        user_id: str,
        session,
        next_status: str,
        agent_update: dict[str, Any],
        job=None,
    ) -> dict[str, Any]:
        """Interview memory is scoped to the current session agent_state only."""
        return {
            **self._empty_interview_memory_updates(),
            "storage": "interview_sessions.report.agent_state",
            "next_status": next_status,
            "session_id": str(getattr(session, "id", "")),
        }

    @staticmethod
    def _interview_memory_scope() -> dict[str, Any]:
        return {
            "short_term": "interview_sessions.report.agent_state",
            "long_term": None,
            "compression": "agent_state.session_summary",
            "shared_fact_sources": ["resumes", "jobs", "applications", "users"],
        }


    @staticmethod
    def _empty_interview_memory_used() -> dict[str, Any]:
        return {
            "assistant_type": INTERVIEW_ASSISTANT_TYPE,
            "count": 0,
            "items": [],
            "compaction": {"compacted": False, "count": 0},
            "memory_snapshot": InterviewService._empty_memory_snapshot(),
        }

    @staticmethod
    def _empty_interview_memory_updates() -> dict[str, Any]:
        return {
            "assistant_type": INTERVIEW_ASSISTANT_TYPE,
            "count": 0,
            "items": [],
            "memory_snapshot": InterviewService._empty_memory_snapshot(),
        }

    @staticmethod
    def _empty_memory_snapshot() -> dict[str, Any]:
        return {
            "available": False,
            "assistant_type": INTERVIEW_ASSISTANT_TYPE,
            "path": None,
            "item_count": 0,
            "char_count": 0,
        }

    @staticmethod
    def _memory_snapshot_for_metadata(
        *,
        memory_context: dict[str, Any] | None,
        memory_updates: dict[str, Any] | None,
    ) -> dict[str, Any]:
        snapshot = (memory_updates or {}).get("memory_snapshot") or (memory_context or {}).get("memory_snapshot")
        if snapshot:
            return AssistantMemoryMarkdownService.public_metadata(snapshot)
        return InterviewService._empty_memory_snapshot()

    @staticmethod
    def _memory_item_summary(memory: dict[str, Any]) -> dict[str, Any]:
        summary = {
            "key": memory.get("key"),
            "memory_kind": memory.get("memory_kind"),
            "scope_type": memory.get("scope_type"),
            "summary": memory.get("summary"),
            "confidence": memory.get("confidence"),
            "source": memory.get("source"),
        }
        if (memory.get("compaction") or {}).get("compacted"):
            summary["compaction"] = memory.get("compaction")
        return summary

    @staticmethod
    def _memory_compaction_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        compactions = [item.get("compaction") or {} for item in items if (item.get("compaction") or {}).get("compacted")]
        return {
            "compacted": bool(compactions),
            "count": sum(int(item.get("count") or 0) for item in compactions),
        }

    def _resolve_resume(self, *, user_id: str, resume_id: str | None):
        resume = (
            self.resume_repository.get_by_id(resume_id=resume_id, user_id=user_id)
            if resume_id
            else self.resume_repository.get_default_by_user_id(user_id=user_id)
        )
        if resume is None:
            raise InterviewServiceError(status_code=400, code=5004, message="Default parsed resume is required")
        if resume.parse_status != "done" or resume.parsed_content is None:
            raise InterviewServiceError(status_code=400, code=5005, message="Resume is not parsed yet")
        return resume

    @classmethod
    def _opening_question_with_resume(cls, *, mode: str, job, resume) -> str:
        parsed = resume.parsed_content or {}
        skills = "、".join([str(item) for item in list(parsed.get("skills") or [])[:6]]) or "暂未识别技能"
        summary = str(parsed.get("summary") or "").strip()[:160] or "简历摘要暂缺"
        jd_summary = str(job.jd_text or "").strip()[:260] or "岗位 JD 暂缺"
        job_skills = "、".join(extract_skills(" ".join([job.title, job.jd_text or ""]))[:6]) or "岗位技能未标注"
        job_type = infer_job_type(job.title, job.jd_text, (job.jd_parsed or {}).get("employment_type") if isinstance(job.jd_parsed, dict) else None)
        focus = cls._job_interview_focus(title=job.title, jd_text=job.jd_text or "")
        return (
            f"你正在面试 {job.company} 的 {job.title}（{job.city or '地点未注明'}，{job_type_label(job_type)}，薪资 {job.salary_range or '未注明'}）。\n"
            f"岗位信息：{jd_summary}\n"
            f"本轮重点：{focus}\n"
            f"我会结合你的简历追问。当前简历：{resume.file_name}；简历技能：{skills}；岗位技能：{job_skills}；简历摘要：{summary}\n\n"
            "请先做一个 1 分钟自我介绍，并重点说明你最匹配这个岗位的一段经历。"
        )

    @staticmethod
    def _job_interview_focus(*, title: str, jd_text: str) -> str:
        text = f"{title} {jd_text}".lower()
        if any(token in text for token in ["后端", "backend", "fastapi", "redis", "接口", "数据库", "服务"]):
            return "围绕接口设计、数据库建模、Redis/缓存、服务稳定性和问题排查追问。"
        if any(token in text for token in ["数据", "data", "sql", "指标", "a/b", "ab test", "analytics"]):
            return "围绕 SQL、指标体系、业务分析、A/B 测试和结论表达追问。"
        if any(token in text for token in ["产品", "product", "用户", "需求", "roadmap", "原型"]):
            return "围绕需求拆解、用户研究、数据判断、原型方案和跨团队推进追问。"
        if any(token in text for token in ["咨询", "consult", "strategy", "商业分析", "行业研究"]):
            return "围绕结构化分析、行业研究、假设拆解、PPT 表达和客户沟通追问。"
        if any(token in text for token in ["金融", "投行", "研究", "风控", "finance", "risk"]):
            return "围绕财务/行业分析、风险判断、Excel 建模和材料表达追问。"
        return "围绕岗位 JD 的核心职责、项目证据和可量化结果追问。"

    def _current_round_info(self, messages: list[dict]) -> dict[str, Any]:
        answered_rounds = [item for item in messages if item.get("role") == "user" and item.get("round_index")]
        round_index = min(len(answered_rounds) + 1, MAX_INTERVIEW_ROUNDS)
        question_id = f"q-{round_index}"
        question = ""
        for item in reversed(messages):
            if item.get("role") == "assistant" and item.get("round_index") == round_index:
                question = str(item.get("content") or "")
                question_id = str(item.get("question_id") or question_id)
                break
        if not question:
            question = "请继续围绕目标岗位回答一个具体项目案例。"
        return {"round_index": round_index, "question_id": question_id, "question": question}

    def _session_state(self, messages: list[dict], report: dict | None) -> dict[str, Any]:
        answered_count = len([item for item in messages if item.get("role") == "user"])
        stored_status = (report or {}).get("status")
        if stored_status == "summary_ready":
            status = "summary"
        elif answered_count >= MAX_INTERVIEW_ROUNDS:
            status = "summary"
        elif messages and messages[-1].get("role") == "assistant":
            status = "waiting_user"
        elif messages and messages[-1].get("role") == "user":
            status = "evaluating"
        else:
            status = "asking"
        return {
            "status": status,
            "round_index": min(max(answered_count + 1, 1), MAX_INTERVIEW_ROUNDS) if status != "summary" else MAX_INTERVIEW_ROUNDS,
            "max_rounds": MAX_INTERVIEW_ROUNDS,
        }

    def _state_report(self, *, messages: list[dict], status: str, agent_state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self._session_state(messages, {"status": "summary_ready"} if status == "summary" else {"status": status})
        scores = [item.get("feedback_score") for item in messages if isinstance(item.get("feedback_score"), (int, float))]
        average_score = round(sum(scores) / len(scores), 2) if scores else None
        report = {
            "status": "summary_ready" if status == "summary" else status,
            "round_index": state["round_index"],
            "max_rounds": MAX_INTERVIEW_ROUNDS,
            "average_feedback_score": average_score,
        }
        if agent_state is not None:
            report["agent_state"] = agent_state
            if status == "summary":
                report["agent_summary"] = build_summary(agent_state)
        return report

    @staticmethod
    def _soft_compress_agent_state(agent_state: dict[str, Any], *, char_limit: int = 1800, keep_recent_rounds: int = 2) -> dict[str, Any]:
        asked_questions = list(agent_state.get("asked_questions") or [])
        total_chars = sum(len(str(item.get("answer") or item.get("candidate_answer") or "")) for item in asked_questions)
        if total_chars <= char_limit or len(asked_questions) <= keep_recent_rounds:
            return agent_state

        cutoff = max(0, len(asked_questions) - keep_recent_rounds)
        compressed = asked_questions[:cutoff]
        summary_lines = []
        for item in compressed:
            question_id = str(item.get("question_id") or item.get("id") or "unknown")
            strategy = str(item.get("followup_strategy") or item.get("strategy") or "")
            answer = str(item.get("answer") or item.get("candidate_answer") or "")
            summary_lines.append(f"{question_id}: {strategy} {answer[:120]}".strip())

        compacted_questions = []
        for index, item in enumerate(asked_questions):
            if index < cutoff:
                compacted = dict(item)
                answer = str(compacted.get("answer") or compacted.get("candidate_answer") or "")
                if answer:
                    compacted["answer"] = answer[:220] + ("..." if len(answer) > 220 else "")
                compacted_questions.append(compacted)
            else:
                compacted_questions.append(item)

        updated = dict(agent_state)
        updated["asked_questions"] = compacted_questions
        updated["session_summary"] = {
            "compressed_round_count": len(compressed),
            "summary": "；".join(summary_lines)[:1200],
            "compression": "soft",
        }
        return updated

    async def _build_feedback(self, *, mode: str, question: str, answer: str, job=None, agent_update: dict | None = None) -> dict:
        rule_feedback = evaluate_answer(answer, mode=mode)
        provider = get_provider()
        feedback_agent = InterviewFeedbackAgent()
        context = AgentContext(provider=provider, request_id="interview-feedback", assistant_type=INTERVIEW_ASSISTANT_TYPE)
        try:
            result = await AgentRunner().run(
                feedback_agent,
                prompt=self._feedback_prompt(mode=mode, question=question, answer=answer, rule_feedback=rule_feedback, job=job, agent_update=agent_update),
                context=context,
            )
        except ClaudeProviderError:
            return rule_feedback

        return {
            **rule_feedback,
            "feedback_text": result.content.strip(),
            "follow_up_question": "请继续用一个具体项目案例支撑你的回答。",
            "agent_name": feedback_agent.agent_name,
        }

    @staticmethod
    def _feedback_prompt(
        *,
        mode: str,
        question: str,
        answer: str,
        rule_feedback: dict,
        job=None,
        agent_update: dict | None = None,
        memory_snapshot_content: str = "",
    ) -> str:
        job_context = ""
        if job is not None:
            job_context = f"目标岗位：{job.company} {job.title}；JD：{str(job.jd_text or '')[:800]}\n"
        agent_context = ""
        if agent_update is not None:
            agent_context = (
                f"回答信号：{agent_update.get('answer_signals')}\n"
                f"持续评分：{agent_update.get('evaluation_state')}\n"
                f"追问策略：{agent_update.get('followup_strategy')}；下一问建议：{agent_update.get('next_prompt')}\n"
            )
        return PromptRegistry().render(
            "interview/feedback",
            {
                "mode": mode,
                "job_context": job_context,
                "question": question,
                "answer": answer,
                "rule_dimensions": rule_feedback["dimensions"],
                "agent_context": agent_context,
            },
        ).user

    def _agent_state_for_session(self, *, session) -> dict[str, Any]:
        report = session.report if isinstance(session.report, dict) else {}
        agent_state = report.get("agent_state")
        if isinstance(agent_state, dict):
            return agent_state
        job = self.job_repository.get_by_id(job_id=str(session.job_id))
        resume = self.resume_repository.get_by_id(resume_id=str(session.resume_id), user_id=str(session.user_id)) if session.resume_id else None
        if job is None or resume is None:
            return {}
        return initialize_interview_agent_state(
            session_id=str(session.id),
            job=job,
            resume=resume,
            round_type=self._round_type_from_mode(session.mode),
        )

    @staticmethod
    def _round_type_from_mode(mode: str) -> str:
        return {
            "standard": "mixed",
            "pressure": "technical",
            "case": "technical",
            "negotiation": "behavioral",
        }.get(mode, "mixed")

    @staticmethod
    def _compose_agent_feedback_text(*, feedback_text: str, next_prompt: str) -> str:
        return f"{feedback_text.strip()}\n\n下一问：{next_prompt.strip()}".strip()

    @staticmethod
    def _summary_prompt(agent_state: dict[str, Any]) -> str:
        summary = build_summary(agent_state)
        risks = "；".join(summary.get("risk_points") or [])
        improvements = "；".join(summary.get("improvement_suggestions") or [])
        return PromptRegistry().render(
            "interview/summary",
            {
                "fit_level": summary["fit_level"],
                "pass_probability": summary["pass_probability"],
                "risks": risks,
                "improvements": improvements,
            },
        ).user
