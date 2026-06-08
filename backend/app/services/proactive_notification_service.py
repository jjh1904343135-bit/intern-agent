from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.agents.notification import NotificationDeciderAgent
from app.agents.runtime import AgentContext, AgentRunner
from app.core.providers.base import LLMProvider
from app.prompts import PromptRegistry
from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.notification_repository import NotificationEventRepository, TelegramAccountRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.telegram_client import TelegramBotClient

REMINDER_WORD = "\u63d0\u9192"


@dataclass(frozen=True)
class ProactiveCandidate:
    user_id: str
    event_key: str
    event_type: str
    event_time: datetime
    title: str
    severity: str
    evidence: dict[str, Any]
    message_hint: str


@dataclass(frozen=True)
class RuleGateResult:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class ProactiveDecision:
    decision: str
    reason: str
    priority: float = 0.0
    message: str = ""
    cooldown_hours: int = 12
    raw: dict[str, Any] = field(default_factory=dict)


class ProactiveRuleGate:
    def __init__(
        self,
        *,
        quiet_start_hour: int,
        quiet_end_hour: int,
        daily_limit: int,
        same_type_cooldown_hours: int,
    ):
        self.quiet_start_hour = quiet_start_hour
        self.quiet_end_hour = quiet_end_hour
        self.daily_limit = daily_limit
        self.same_type_cooldown_hours = same_type_cooldown_hours

    def evaluate(
        self,
        *,
        candidate: ProactiveCandidate,
        now: datetime,
        sent_today_count: int,
        last_same_type_sent_at: datetime | None,
        last_event_sent_at: datetime | None,
        effective_same_type_cooldown_hours: int | None = None,
    ) -> RuleGateResult:
        if _is_quiet_hour(now.hour, self.quiet_start_hour, self.quiet_end_hour):
            return RuleGateResult(False, "quiet_hours")
        if sent_today_count >= self.daily_limit:
            return RuleGateResult(False, "daily_limit")
        if last_event_sent_at is not None:
            return RuleGateResult(False, "event_already_sent")
        cooldown_hours = effective_same_type_cooldown_hours or self.same_type_cooldown_hours
        if last_same_type_sent_at and now - last_same_type_sent_at < timedelta(hours=cooldown_hours):
            return RuleGateResult(False, "same_type_cooldown")
        return RuleGateResult(True, "allowed")


class ProactiveNotificationDecider:
    def __init__(self, *, provider: LLMProvider, timezone_name: str):
        self.provider = provider
        self.timezone_name = timezone_name
        self.timezone = _resolve_timezone(timezone_name)

    async def decide(
        self,
        *,
        candidate: ProactiveCandidate,
        now: datetime,
        recent_pushes: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> ProactiveDecision:
        prompt = self._build_prompt(
            candidate=candidate,
            now=now,
            recent_pushes=recent_pushes,
            user_context=user_context,
        )
        agent = NotificationDeciderAgent()
        context = AgentContext(provider=self.provider, request_id=f"notification:{candidate.event_key}", assistant_type=agent.assistant_type)
        result = await AgentRunner().run(agent, prompt=prompt, context=context)
        try:
            payload = json.loads(_extract_json_object(result.content))
        except Exception:
            return ProactiveDecision(decision="skip", reason="llm_invalid_response", raw={"text": result.content[:500]})
        decision = str(payload.get("decision") or "skip").strip().lower()
        if decision != "send":
            return ProactiveDecision(
                decision="skip",
                reason=str(payload.get("reason") or "llm_skip"),
                priority=float(payload.get("priority") or 0.0),
                raw=payload,
            )
        message = _ensure_timestamp_prefix(str(payload.get("message") or ""), now=now)
        if not message.strip():
            return ProactiveDecision(decision="skip", reason="llm_empty_message", raw=payload)
        return ProactiveDecision(
            decision="send",
            reason=str(payload.get("reason") or "llm_send"),
            priority=float(payload.get("priority") or 0.0),
            message=message,
            cooldown_hours=_parse_cooldown_hours(payload.get("cooldown_hours"), default=12),
            raw=payload,
        )

    def _build_prompt(
        self,
        *,
        candidate: ProactiveCandidate,
        now: datetime,
        recent_pushes: list[dict[str, Any]],
        user_context: dict[str, Any],
    ) -> str:
        local_now = _localize(now, self.timezone)
        local_event_time = _localize(candidate.event_time, self.timezone)
        return PromptRegistry().render(
            "notification/proactive_decision",
            {
                "local_now": f"{local_now:%Y-%m-%d %H:%M}",
                "timezone_name": self.timezone_name,
                "event_type": candidate.event_type,
                "event_key": candidate.event_key,
                "event_time": f"{local_event_time:%Y-%m-%d %H:%M}",
                "title": candidate.title,
                "severity": candidate.severity,
                "evidence_json": json.dumps(candidate.evidence, ensure_ascii=False, default=str),
                "message_hint": candidate.message_hint,
                "user_context_json": json.dumps(user_context, ensure_ascii=False, default=str),
                "recent_pushes_json": json.dumps(recent_pushes, ensure_ascii=False, default=str),
            },
        ).user


class ProactiveNotificationService:
    def __init__(
        self,
        *,
        db: Session,
        bot_client: TelegramBotClient,
        provider: LLMProvider,
        timezone_name: str,
        quiet_start_hour: int,
        quiet_end_hour: int,
        daily_limit: int,
        same_type_cooldown_hours: int,
        allowed_chat_ids: set[str] | None = None,
    ):
        self.db = db
        self.bot_client = bot_client
        self.decider = ProactiveNotificationDecider(provider=provider, timezone_name=timezone_name)
        self.gate = ProactiveRuleGate(
            quiet_start_hour=quiet_start_hour,
            quiet_end_hour=quiet_end_hour,
            daily_limit=daily_limit,
            same_type_cooldown_hours=same_type_cooldown_hours,
        )
        self.timezone = _resolve_timezone(timezone_name)
        self.allowed_chat_ids = allowed_chat_ids or set()

    async def tick_once(self, *, now: datetime | None = None, limit: int = 10) -> int:
        now = now or datetime.now(self.timezone).replace(tzinfo=None)
        event_repository = NotificationEventRepository(self.db)
        sent_count = 0
        for account in TelegramAccountRepository(self.db).list_enabled(limit=limit):
            if self.allowed_chat_ids and not _account_allowed(account, self.allowed_chat_ids):
                continue
            candidates = self._build_candidates(user_id=str(account.user_id), now=now)
            for candidate in candidates:
                last_same_type_event = event_repository.last_sent_event(
                    user_id=str(account.user_id),
                    channel="telegram",
                    event_type=candidate.event_type,
                )
                gate_result = self.gate.evaluate(
                    candidate=candidate,
                    now=now,
                    sent_today_count=event_repository.count_sent_today(user_id=str(account.user_id), channel="telegram", now=now),
                    last_same_type_sent_at=last_same_type_event.sent_at if last_same_type_event is not None else None,
                    last_event_sent_at=event_repository.last_sent_at(
                        user_id=str(account.user_id),
                        channel="telegram",
                        event_key=candidate.event_key,
                    ),
                    effective_same_type_cooldown_hours=_decision_cooldown_hours(last_same_type_event),
                )
                if not gate_result.allowed:
                    if event_repository.should_record_skip(candidate=candidate, channel="telegram", reason=gate_result.reason, now=now):
                        event_repository.record_skip(candidate=candidate, channel="telegram", reason=gate_result.reason, now=now)
                    continue
                decision = await self.decider.decide(
                    candidate=candidate,
                    now=now,
                    recent_pushes=event_repository.recent_sent(user_id=str(account.user_id), channel="telegram", limit=5),
                    user_context={},
                )
                if decision.decision != "send":
                    if event_repository.should_record_skip(candidate=candidate, channel="telegram", reason=decision.reason, now=now):
                        event_repository.record_skip(candidate=candidate, channel="telegram", reason=decision.reason, now=now, decision=decision.raw)
                    continue
                result = self.bot_client.send_message(chat_id=str(account.chat_id), text=decision.message)
                if result.ok:
                    event_repository.record_sent(candidate=candidate, channel="telegram", decision=decision, now=now)
                    sent_count += 1
                else:
                    event_repository.record_failed(
                        candidate=candidate,
                        channel="telegram",
                        reason=result.error or "telegram_send_failed",
                        now=now,
                        decision=decision.raw,
                    )
        return sent_count

    def _build_candidates(self, *, user_id: str, now: datetime) -> list[ProactiveCandidate]:
        application_repository = ApplicationRepository(self.db)
        applications = application_repository.list_by_statuses(
            statuses=["saved", "opened", "applied_manual", "waiting_feedback"],
            user_id=user_id,
            limit=50,
        )
        job_ids = [str(item.job_id) for item in applications]
        jobs = JobRepository(self.db).get_by_ids(job_ids)
        candidates = build_application_followup_candidates(
            applications=applications,
            jobs_by_id={str(job.id): job for job in jobs},
            now=now,
        )
        latest_resume = ResumeRepository(self.db).get_latest_by_user_id(user_id=user_id)
        if latest_resume is not None:
            resume_candidate = build_resume_status_candidate(resume=latest_resume)
            if resume_candidate is not None:
                candidates.append(resume_candidate)
        return candidates


def build_application_followup_candidates(
    *,
    applications: list[Any],
    jobs_by_id: dict[str, Any],
    now: datetime,
) -> list[ProactiveCandidate]:
    candidates: list[ProactiveCandidate] = []
    thresholds = {"saved": 24, "opened": 12, "applied_manual": 48, "waiting_feedback": 48}
    status_labels = {
        "saved": "saved but not applied",
        "opened": "opened original site but not confirmed",
        "applied_manual": "applied and awaiting follow-up notes",
        "waiting_feedback": "waiting for feedback",
    }
    for application in applications:
        status = str(application.status)
        threshold = thresholds.get(status)
        if threshold is None:
            continue
        event_time = application.status_updated_at or application.created_at
        elapsed_hours = int(max(0, (now - event_time).total_seconds()) // 3600)
        if elapsed_hours < threshold:
            continue
        job = jobs_by_id.get(str(application.job_id))
        company = str(getattr(job, "company", "target company") or "target company")
        title = str(getattr(job, "title", "target role") or "target role")
        label = status_labels.get(status, status)
        candidates.append(
            ProactiveCandidate(
                user_id=str(application.user_id),
                event_key=f"application_followup:{application.id}:{status}",
                event_type="application_followup",
                event_time=event_time,
                title=f"{company} {title}: {label} for {elapsed_hours} hours",
                severity="medium" if status in {"applied_manual", "waiting_feedback"} else "low",
                evidence={
                    "application_id": str(application.id),
                    "job_id": str(application.job_id),
                    "status": status,
                    "company": company,
                    "job_title": title,
                    "elapsed_hours": elapsed_hours,
                },
                message_hint="Nudge the user to update application follow-up notes or take the next action.",
            )
        )
    return candidates


def build_resume_status_candidate(*, resume: Any) -> ProactiveCandidate | None:
    status = str(getattr(resume, "parse_status", "") or "")
    if status not in {"done", "failed"}:
        return None
    event_time = getattr(resume, "updated_at", None) or getattr(resume, "created_at", None)
    if event_time is None:
        return None
    score_report = getattr(resume, "score_report", None) or {}
    risks = [str(item) for item in list(score_report.get("risks") or [])[:2]]
    overall_score = score_report.get("overall_score")
    file_name = str(getattr(resume, "file_name", "resume") or "resume")
    if status == "done":
        title = f"{file_name} resume parsing completed"
        hint = "Tell the user the resume is ready, and suggest checking score and risks."
        if risks:
            hint += f" Mention these risks first: {'; '.join(risks)}."
        severity = "medium" if risks else "low"
    else:
        parse_error = getattr(resume, "parse_error", "") or "unknown error"
        title = f"{file_name} resume parsing failed"
        hint = f"Tell the user parsing failed and suggest uploading a cleaner file. Error: {parse_error}"
        severity = "high"
    return ProactiveCandidate(
        user_id=str(resume.user_id),
        event_key=f"resume_status:{resume.id}:{status}",
        event_type="resume_status",
        event_time=event_time,
        title=title,
        severity=severity,
        evidence={
            "resume_id": str(resume.id),
            "file_name": file_name,
            "parse_status": status,
            "overall_score": overall_score,
            "risks": risks,
        },
        message_hint=hint,
    )


def _account_allowed(account: Any, allowed_values: set[str]) -> bool:
    chat_id = str(getattr(account, "chat_id", "") or "").strip()
    username = str(getattr(account, "username", "") or "").strip().lstrip("@")
    normalized = {str(item).strip().lstrip("@") for item in allowed_values if str(item).strip()}
    return chat_id in normalized or bool(username and username in normalized)


def _decision_cooldown_hours(event: Any | None) -> int | None:
    if event is None or not isinstance(getattr(event, "decision", None), dict):
        return None
    return _parse_cooldown_hours(event.decision.get("cooldown_hours"), default=None)


def _parse_cooldown_hours(value: Any, *, default: int | None) -> int | None:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _is_quiet_hour(hour: int, quiet_start: int, quiet_end: int) -> bool:
    if quiet_start == quiet_end:
        return False
    if quiet_start < quiet_end:
        return quiet_start <= hour < quiet_end
    return hour >= quiet_start or hour < quiet_end


def _extract_json_object(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    raise ValueError("no json object")


def _ensure_timestamp_prefix(message: str, *, now: datetime) -> str:
    stripped = (message or "").strip()
    prefix = f"{now:%H:%M} {REMINDER_WORD}: "
    if len(stripped) >= 6 and stripped[0:2].isdigit() and stripped[2] == ":" and stripped[3:5].isdigit():
        return stripped
    return f"{prefix}{stripped}"


def _resolve_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        if timezone_name == "Asia/Shanghai":
            return timezone(timedelta(hours=8))
        return timezone.utc


def _localize(value: datetime, timezone_value) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone_value)
    return value.replace(tzinfo=timezone_value)
