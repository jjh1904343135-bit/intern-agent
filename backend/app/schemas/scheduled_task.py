from typing import Literal

from pydantic import BaseModel, Field


class UpdateScheduledTaskRequest(BaseModel):
    status: Literal["enabled", "paused", "cancelled"] = Field(...)


class ScheduledTaskItem(BaseModel):
    task_id: str
    title: str
    instruction: str
    status: str
    schedule_type: str
    schedule_value: dict
    schedule_label: str
    timezone: str | None = None
    next_run_at: str | None = None
    next_run_at_local: str | None = None
    last_run_at: str | None = None
    source_channel: str | None = None
    delivery_channel: str | None = None
    deliver: bool = True
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
