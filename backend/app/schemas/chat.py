from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatStreamRequest(BaseModel):
    message: str | None = Field(default=None, max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)
    action: Literal["send", "regenerate", "continue"] = "send"

    @field_validator("session_id", mode="before")
    @classmethod
    def normalize_session_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ChatStreamRequest":
        if self.action == "send" and not self.message:
            raise ValueError("message is required when action is send")
        if self.action in {"regenerate", "continue"} and not self.session_id:
            raise ValueError("session_id is required when action is regenerate or continue")
        return self


class ChatSessionSummary(BaseModel):
    session_id: str
    title: str
    preview: str
    message_count: int
    updated_at: str | None
    created_at: str | None


class ChatSessionDetail(BaseModel):
    session_id: str
    messages: list[dict]
    agent_states: dict | None
    updated_at: str | None
    created_at: str | None
