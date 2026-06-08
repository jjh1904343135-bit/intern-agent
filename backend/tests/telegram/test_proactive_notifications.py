from __future__ import annotations

import json
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import text

from app.core.database import session_local

from app.repositories.notification_repository import NotificationEventRepository
from app.services import proactive_notification_service as notification_module
from app.services.proactive_notification_service import (
    ProactiveCandidate,
    ProactiveDecision,
    ProactiveNotificationDecider,
    ProactiveNotificationService,
    ProactiveRuleGate,
    _decision_cooldown_hours,
    build_application_followup_candidates,
    build_resume_status_candidate,
)


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, response: dict):
        self.response = response
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs):
        self.prompts.append(prompt)
        return json.dumps(self.response, ensure_ascii=False)


def test_application_followup_candidate_uses_status_timestamp() -> None:
    status_updated_at = datetime(2026, 5, 27, 18, 20)
    now = datetime(2026, 5, 30, 10, 30)
    application = SimpleNamespace(
        id="app-1",
        user_id="user-1",
        job_id="job-1",
        status="waiting_feedback",
        status_updated_at=status_updated_at,
        created_at=status_updated_at,
    )
    job = SimpleNamespace(id="job-1", company="Tencent", title="Java Backend Intern", city="Beijing")

    candidates = build_application_followup_candidates(
        applications=[application],
        jobs_by_id={"job-1": job},
        now=now,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.event_time == status_updated_at
    assert candidate.event_key == "application_followup:app-1:waiting_feedback"
    assert "waiting for feedback" in candidate.title
    assert candidate.evidence["elapsed_hours"] == 64


def test_resume_status_candidate_uses_resume_updated_timestamp() -> None:
    updated_at = datetime(2026, 5, 30, 9, 45)
    resume = SimpleNamespace(
        id="resume-1",
        user_id="user-1",
        file_name="resume.pdf",
        parse_status="done",
        updated_at=updated_at,
        score_report={"overall_score": 82, "risks": ["project metrics are weak"]},
        parse_error=None,
    )

    candidate = build_resume_status_candidate(resume=resume)

    assert candidate is not None
    assert candidate.event_time == updated_at
    assert candidate.event_key == "resume_status:resume-1:done"
    assert candidate.event_type == "resume_status"
    assert candidate.evidence["overall_score"] == 82
    assert "project metrics are weak" in candidate.message_hint


def test_empty_profile_does_not_create_daily_onboarding_nudge(monkeypatch) -> None:
    class FakeApplicationRepository:
        def __init__(self, db):
            pass

        def list_by_statuses(self, **kwargs):
            return []

    class FakeJobRepository:
        def __init__(self, db):
            pass

        def get_by_ids(self, job_ids):
            return []

    class FakeResumeRepository:
        def __init__(self, db):
            pass

        def get_latest_by_user_id(self, *, user_id: str):
            return None

    monkeypatch.setattr(notification_module, "ApplicationRepository", FakeApplicationRepository)
    monkeypatch.setattr(notification_module, "JobRepository", FakeJobRepository)
    monkeypatch.setattr(notification_module, "ResumeRepository", FakeResumeRepository)
    service = ProactiveNotificationService(
        db=SimpleNamespace(),
        bot_client=SimpleNamespace(),
        provider=FakeProvider({"decision": "skip"}),
        timezone_name="Asia/Shanghai",
        quiet_start_hour=23,
        quiet_end_hour=8,
        daily_limit=3,
        same_type_cooldown_hours=12,
    )

    assert service._build_candidates(user_id="user-1", now=datetime(2026, 6, 7, 9, 30)) == []


def test_rule_gate_blocks_quiet_hours_daily_limit_and_dynamic_cooldown() -> None:
    candidate = ProactiveCandidate(
        user_id="user-1",
        event_key="k",
        event_type="application_followup",
        event_time=datetime(2026, 5, 30, 1, 10),
        title="night reminder",
        severity="medium",
        evidence={},
        message_hint="",
    )
    gate = ProactiveRuleGate(
        quiet_start_hour=23,
        quiet_end_hour=8,
        daily_limit=2,
        same_type_cooldown_hours=12,
    )

    quiet = gate.evaluate(
        candidate=candidate,
        now=datetime(2026, 5, 30, 1, 30),
        sent_today_count=0,
        last_same_type_sent_at=None,
        last_event_sent_at=None,
    )
    limited = gate.evaluate(
        candidate=candidate,
        now=datetime(2026, 5, 30, 10, 30),
        sent_today_count=2,
        last_same_type_sent_at=None,
        last_event_sent_at=None,
    )
    dynamic_cooldown = gate.evaluate(
        candidate=candidate,
        now=datetime(2026, 5, 30, 22, 30),
        sent_today_count=0,
        last_same_type_sent_at=datetime(2026, 5, 30, 10, 30),
        last_event_sent_at=None,
        effective_same_type_cooldown_hours=24,
    )
    default_cooldown_expired = gate.evaluate(
        candidate=candidate,
        now=datetime(2026, 5, 30, 22, 31),
        sent_today_count=0,
        last_same_type_sent_at=datetime(2026, 5, 30, 10, 30),
        last_event_sent_at=None,
    )

    assert quiet.allowed is False
    assert quiet.reason == "quiet_hours"
    assert limited.allowed is False
    assert limited.reason == "daily_limit"
    assert dynamic_cooldown.allowed is False
    assert dynamic_cooldown.reason == "same_type_cooldown"
    assert default_cooldown_expired.allowed is True


def test_recorded_llm_cooldown_can_be_used_by_next_gate() -> None:
    user_id = "00000000-0000-0000-0000-00000000c001"
    candidate = ProactiveCandidate(
        user_id=user_id,
        event_key="application_followup:cooldown",
        event_type="application_followup",
        event_time=datetime(2026, 5, 30, 9, 0),
        title="cooldown test",
        severity="medium",
        evidence={"application_id": "app-cooldown"},
        message_hint="",
    )
    with session_local() as session:
        session.execute(text("DELETE FROM notification_events WHERE user_id = :user_id"), {"user_id": user_id})
        session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        session.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, name, quota_reset_at)
                VALUES (:user_id, 'cooldown@example.com', 'hash', 'Cooldown User', now())
                """
            ),
            {"user_id": user_id},
        )
        repository = NotificationEventRepository(session)
        repository.record_sent(
            candidate=candidate,
            channel="telegram",
            decision=ProactiveDecision(
                decision="send",
                reason="llm_send",
                message="10:00 提醒: test",
                cooldown_hours=24,
                raw={},
            ),
            now=datetime(2026, 5, 30, 10, 0),
        )

        event = repository.last_sent_event(user_id=user_id, channel="telegram", event_type="application_followup")

    assert event is not None
    assert event.decision["cooldown_hours"] == 24
    assert _decision_cooldown_hours(event) == 24


def test_notification_reason_is_truncated_to_database_limit() -> None:
    user_id = "00000000-0000-0000-0000-00000000c002"
    long_reason = "x" * 300
    candidate = ProactiveCandidate(
        user_id=user_id,
        event_key="onboarding_nudge:truncate",
        event_type="onboarding_nudge",
        event_time=datetime(2026, 6, 7, 9, 0),
        title="truncate test",
        severity="low",
        evidence={},
        message_hint="",
    )
    with session_local() as session:
        session.execute(text("DELETE FROM notification_events WHERE user_id = :user_id"), {"user_id": user_id})
        session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
        session.execute(
            text(
                """
                INSERT INTO users (id, email, password_hash, name, quota_reset_at)
                VALUES (:user_id, 'truncate@example.com', 'hash', 'Truncate User', now())
                """
            ),
            {"user_id": user_id},
        )
        event = NotificationEventRepository(session).record_sent(
            candidate=candidate,
            channel="telegram",
            decision=ProactiveDecision(decision="send", reason=long_reason, message="test", raw={}),
            now=datetime(2026, 6, 7, 9, 0),
        )

    assert event.reason == "x" * 120


def test_service_uses_recorded_cooldown_before_llm_decision(monkeypatch) -> None:
    candidate = ProactiveCandidate(
        user_id="user-1",
        event_key="application_followup:next",
        event_type="application_followup",
        event_time=datetime(2026, 5, 30, 9, 0),
        title="next follow-up",
        severity="medium",
        evidence={"application_id": "app-next"},
        message_hint="",
    )
    last_event = SimpleNamespace(sent_at=datetime(2026, 5, 30, 10, 0), decision={"cooldown_hours": 24})

    class FakeEventRepository:
        def __init__(self, db):
            self.skips: list[tuple[str, str]] = []

        def last_sent_event(self, **kwargs):
            assert kwargs["event_type"] == "application_followup"
            return last_event

        def count_sent_today(self, **kwargs):
            return 0

        def last_sent_at(self, **kwargs):
            return None

        def should_record_skip(self, **kwargs):
            return True

        def record_skip(self, **kwargs):
            self.skips.append((kwargs["candidate"].event_key, kwargs["reason"]))

        def recent_sent(self, **kwargs):
            return []

    class FakeAccountRepository:
        def __init__(self, db):
            pass

        def list_enabled(self, *, limit: int = 50):
            return [SimpleNamespace(user_id="user-1", chat_id="42")]

    class FakeBotClient:
        def send_message(self, *, chat_id: str, text: str):
            raise AssertionError("cooldown should block before sending")

    class FakeProvider:
        name = "fake"
        model = "fake-model"

        async def generate(self, prompt: str, **kwargs):
            raise AssertionError("cooldown should block before LLM decision")

    event_repositories: list[FakeEventRepository] = []

    def fake_event_repository(db):
        repository = FakeEventRepository(db)
        event_repositories.append(repository)
        return repository

    monkeypatch.setattr(notification_module, "NotificationEventRepository", fake_event_repository)
    monkeypatch.setattr(notification_module, "TelegramAccountRepository", FakeAccountRepository)

    service = ProactiveNotificationService(
        db=SimpleNamespace(),
        bot_client=FakeBotClient(),
        provider=FakeProvider(),
        timezone_name="Asia/Shanghai",
        quiet_start_hour=23,
        quiet_end_hour=8,
        daily_limit=3,
        same_type_cooldown_hours=12,
    )
    service._build_candidates = lambda user_id, now: [candidate]

    sent_count = asyncio.run(service.tick_once(now=datetime(2026, 5, 30, 22, 30)))

    assert sent_count == 0
    assert event_repositories[0].skips == [("application_followup:next", "same_type_cooldown")]


def test_service_skips_accounts_outside_allowed_chat_ids(monkeypatch) -> None:
    candidate = ProactiveCandidate(
        user_id="user-1",
        event_key="onboarding_nudge:2026-06-07",
        event_type="onboarding_nudge",
        event_time=datetime(2026, 6, 7, 9, 0),
        title="setup reminder",
        severity="low",
        evidence={},
        message_hint="",
    )

    class FakeEventRepository:
        def __init__(self, db):
            pass

        def last_sent_event(self, **kwargs):
            return None

        def count_sent_today(self, **kwargs):
            return 0

        def last_sent_at(self, **kwargs):
            return None

        def recent_sent(self, **kwargs):
            return []

        def record_sent(self, **kwargs):
            return None

    class FakeAccountRepository:
        def __init__(self, db):
            pass

        def list_enabled(self, *, limit: int = 50):
            return [
                SimpleNamespace(user_id="user-1", chat_id="not-allowed", username="bad"),
                SimpleNamespace(user_id="user-1", chat_id="42", username="allowed_user"),
            ]

    class FakeBotClient:
        sent: list[str] = []

        def send_message(self, *, chat_id: str, text: str):
            self.sent.append(chat_id)
            return SimpleNamespace(ok=True)

    class FakeProvider:
        name = "fake"
        model = "fake-model"

        async def generate(self, prompt: str, **kwargs):
            return json.dumps({"decision": "send", "reason": "test", "message": "test"})

    monkeypatch.setattr(notification_module, "NotificationEventRepository", FakeEventRepository)
    monkeypatch.setattr(notification_module, "TelegramAccountRepository", FakeAccountRepository)
    bot_client = FakeBotClient()
    service = ProactiveNotificationService(
        db=SimpleNamespace(),
        bot_client=bot_client,
        provider=FakeProvider(),
        timezone_name="Asia/Shanghai",
        quiet_start_hour=23,
        quiet_end_hour=8,
        daily_limit=3,
        same_type_cooldown_hours=12,
        allowed_chat_ids={"42"},
    )
    service._build_candidates = lambda user_id, now: [candidate]
    monkeypatch.setattr(service.gate, "evaluate", lambda **kwargs: SimpleNamespace(allowed=True, reason="allowed"))

    sent_count = asyncio.run(service.tick_once(now=datetime(2026, 6, 7, 9, 0)))

    assert sent_count == 1
    assert bot_client.sent == ["42"]



def test_llm_decider_requires_timestamped_send_or_skip() -> None:
    candidate = ProactiveCandidate(
        user_id="user-1",
        event_key="application_followup:app-1:waiting_feedback",
        event_type="application_followup",
        event_time=datetime(2026, 5, 27, 18, 20),
        title="Tencent Java Backend Intern waiting for feedback for 64 hours",
        severity="medium",
        evidence={"elapsed_hours": 64},
        message_hint="Nudge the user to update follow-up notes.",
    )
    provider = FakeProvider(
        {
            "decision": "send",
            "reason": "waiting more than two days with a clear next action",
            "priority": 0.82,
            "message": "\u817e\u8baf Java \u540e\u7aef\u5b9e\u4e60\u5df2\u7b49\u5f85\u53cd\u9988 64 \u5c0f\u65f6\uff0c\u5efa\u8bae\u4eca\u5929\u8865\u4e00\u6761\u8ddf\u8fdb\u8bb0\u5f55\u3002",
            "cooldown_hours": 12,
        }
    )
    decider = ProactiveNotificationDecider(provider=provider, timezone_name="Asia/Shanghai")

    decision = asyncio.run(
        decider.decide(
            candidate=candidate,
            now=datetime(2026, 5, 30, 10, 30),
            recent_pushes=[],
            user_context={"preferences": ["Java Backend", "Beijing"]},
        )
    )

    assert decision.decision == "send"
    assert decision.message.startswith("10:30 \u63d0\u9192:")
    assert decision.cooldown_hours == 12
    assert "Current local time: 2026-05-30 10:30" in provider.prompts[0]
    assert "event_time=2026-05-27 18:20" in provider.prompts[0]


def test_llm_decider_falls_back_to_skip_on_invalid_json() -> None:
    class InvalidProvider:
        name = "fake"
        model = "fake-model"

        async def generate(self, prompt: str, **kwargs):
            return "not-json"

    decider = ProactiveNotificationDecider(provider=InvalidProvider(), timezone_name="Asia/Shanghai")
    decision = asyncio.run(
        decider.decide(
            candidate=ProactiveCandidate(
                user_id="user-1",
                event_key="k",
                event_type="resume_done",
                event_time=datetime(2026, 5, 30, 10, 0),
                title="resume parsing completed",
                severity="low",
                evidence={},
                message_hint="",
            ),
            now=datetime(2026, 5, 30, 10, 30),
            recent_pushes=[],
            user_context={},
        )
    )

    assert decision.decision == "skip"
    assert decision.reason == "llm_invalid_response"
