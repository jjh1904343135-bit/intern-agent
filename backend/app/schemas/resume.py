from __future__ import annotations

from pydantic import BaseModel


class ResumeUploadResponse(BaseModel):
    resume_id: str
    parse_status: str
    estimated_seconds: int
    progress: dict


class ResumeStatusResponse(BaseModel):
    resume_id: str
    parse_status: str
    file_name: str
    parsed_content: dict | None
    parse_error: str | None
    score: dict | None = None
    progress: dict
