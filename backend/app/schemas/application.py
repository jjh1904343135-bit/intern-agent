from pydantic import BaseModel, Field


class CreateApplicationRequest(BaseModel):
    cover_letter: str | None = Field(default=None, max_length=2000)


class UpdateApplicationNotesRequest(BaseModel):
    """Manual follow-up notes kept with an application record."""
    platform: str | None = Field(default=None, max_length=120)
    applied_date: str | None = Field(default=None, max_length=32)
    hr_contact: str | None = Field(default=None, max_length=200)
    feedback_result: str | None = Field(default=None, max_length=1000)
