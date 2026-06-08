from pydantic import BaseModel, Field


class StartInterviewRequest(BaseModel):
    job_id: str = Field(min_length=36, max_length=36)
    mode: str = Field(pattern="^(standard|pressure|case|negotiation)$")
    resume_id: str | None = Field(default=None, min_length=36, max_length=36)
    force_new: bool = False


class SubmitInterviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=5, max_length=3000)
