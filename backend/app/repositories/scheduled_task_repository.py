from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, String, cast, select
from sqlalchemy.orm import Session

from app.models.scheduled_task import AssistantScheduledTask, AssistantScheduledTaskRun, AssistantTaskInbox


class ScheduledTaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_task(self, **kwargs) -> AssistantScheduledTask:
        task = AssistantScheduledTask(**kwargs)
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def list_tasks(self, *, user_id: str, limit: int = 30) -> list[AssistantScheduledTask]:
        stmt: Select[tuple[AssistantScheduledTask]] = (
            select(AssistantScheduledTask)
            .where(AssistantScheduledTask.user_id == user_id, AssistantScheduledTask.status != "cancelled")
            .order_by(AssistantScheduledTask.next_run_at.asc().nullslast(), AssistantScheduledTask.updated_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def find_task(self, *, user_id: str, selector: str) -> AssistantScheduledTask | None:
        normalized = str(selector or "").strip()
        if not normalized:
            return None
        stmt: Select[tuple[AssistantScheduledTask]] = (
            select(AssistantScheduledTask)
            .where(
                AssistantScheduledTask.user_id == user_id,
                cast(AssistantScheduledTask.id, String).like(f"{normalized}%"),
            )
            .order_by(AssistantScheduledTask.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def update_status(self, *, task: AssistantScheduledTask, status: str) -> AssistantScheduledTask:
        task.status = status
        task.updated_at = datetime.utcnow()
        if status in {"paused", "cancelled"}:
            task.locked_at = None
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def claim_due_tasks(self, *, now: datetime, limit: int = 5) -> list[AssistantScheduledTask]:
        stale_before = now - timedelta(minutes=15)
        stmt: Select[tuple[AssistantScheduledTask]] = (
            select(AssistantScheduledTask)
            .where(
                AssistantScheduledTask.next_run_at.is_not(None),
                AssistantScheduledTask.next_run_at <= now,
                (
                    (AssistantScheduledTask.status == "enabled")
                    | ((AssistantScheduledTask.status == "running") & (AssistantScheduledTask.locked_at < stale_before))
                ),
            )
            .order_by(AssistantScheduledTask.next_run_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        tasks = list(self.db.execute(stmt).scalars())
        for task in tasks:
            task.status = "running"
            task.locked_at = now
            task.updated_at = now
            self.db.add(task)
        self.db.commit()
        for task in tasks:
            self.db.refresh(task)
        return tasks

    def create_run(self, *, task: AssistantScheduledTask, now: datetime) -> AssistantScheduledTaskRun:
        run = AssistantScheduledTaskRun(task_id=str(task.id), user_id=str(task.user_id), started_at=now, status="running")
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def finish_run(
        self,
        *,
        run: AssistantScheduledTaskRun,
        status: str,
        output: str | None,
        error: str | None,
        metadata: dict[str, Any] | None,
        now: datetime,
    ) -> AssistantScheduledTaskRun:
        run.status = status
        run.output = output
        run.error = error
        run.run_metadata = metadata or {}
        run.finished_at = now
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_task_success(self, *, task: AssistantScheduledTask, next_run_at: datetime | None, status: str, now: datetime) -> AssistantScheduledTask:
        task.status = status
        task.last_run_at = now
        task.next_run_at = next_run_at
        task.locked_at = None
        task.last_error = None
        task.updated_at = now
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def mark_task_failed(self, *, task: AssistantScheduledTask, error: str, now: datetime) -> AssistantScheduledTask:
        task.status = "enabled"
        task.locked_at = None
        task.last_error = error[:1000]
        task.next_run_at = now + timedelta(minutes=5)
        task.updated_at = now
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def record_inbox(self, **kwargs) -> AssistantTaskInbox:
        item = AssistantTaskInbox(**kwargs)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_inbox(self, *, user_id: str, limit: int = 30) -> list[AssistantTaskInbox]:
        stmt: Select[tuple[AssistantTaskInbox]] = (
            select(AssistantTaskInbox)
            .where(AssistantTaskInbox.user_id == user_id)
            .order_by(AssistantTaskInbox.created_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())

    def mark_inbox_read(self, *, user_id: str, inbox_id: str, now: datetime) -> AssistantTaskInbox | None:
        stmt = select(AssistantTaskInbox).where(AssistantTaskInbox.id == inbox_id, AssistantTaskInbox.user_id == user_id).limit(1)
        item = self.db.execute(stmt).scalar_one_or_none()
        if item is None:
            return None
        item.status = "read"
        item.read_at = now
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_runs(self, *, user_id: str, task_id: str, limit: int = 20) -> list[AssistantScheduledTaskRun]:
        stmt: Select[tuple[AssistantScheduledTaskRun]] = (
            select(AssistantScheduledTaskRun)
            .where(AssistantScheduledTaskRun.user_id == user_id, AssistantScheduledTaskRun.task_id == task_id)
            .order_by(AssistantScheduledTaskRun.started_at.desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).scalars())
