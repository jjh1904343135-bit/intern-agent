from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


InterviewLevel = Literal["intern", "junior", "mid", "senior", "staff", "manager"]
RoundType = Literal["screening", "technical", "hm", "behavioral", "mixed"]
QuestionCategory = Literal["experience", "technical", "system_design", "behavioral", "coding"]
FollowupStrategy = Literal["clarify", "drill_down", "challenge", "transfer"]


@dataclass
class JobProfile:
    title: str
    company: str | None = None
    level: InterviewLevel = "intern"
    domain_tags: list[str] = field(default_factory=list)
    must_have_skills: list[str] = field(default_factory=list)
    nice_to_have_skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    interview_focus: list[str] = field(default_factory=list)
    language: Literal["zh", "en", "mixed"] = "zh"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CandidateProfile:
    resume_id: str
    file_name: str | None = None
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    experience: list[dict] = field(default_factory=list)
    education: list[dict] = field(default_factory=list)
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PlannedQuestion:
    id: str
    category: QuestionCategory
    skill_tag: str
    prompt: str
    ideal_signals: list[str]
    followup_axes: list[str]
    difficulty: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnswerSignals:
    completeness: int
    correctness: int
    depth: int
    specificity: int
    ownership: int
    red_flags: list[str] = field(default_factory=list)
    mentioned_skills: list[str] = field(default_factory=list)
    missing_expected_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvaluationState:
    technical_depth: int = 1
    practical_experience: int = 1
    communication: int = 1
    problem_solving: int = 1
    ownership: int = 1
    role_fit: int = 1
    confidence: int = 1
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InterviewAgentState:
    session_id: str
    job_profile: dict
    candidate_profile: dict
    round_type: RoundType
    question_plan: list[dict]
    asked_questions: list[dict] = field(default_factory=list)
    evaluation_state: dict = field(default_factory=lambda: EvaluationState().to_dict())
    difficulty: int = 2
    remaining_focus: list[str] = field(default_factory=list)
    last_followup_strategy: FollowupStrategy | None = None
    mcp_hooks: dict = field(default_factory=lambda: {"enabled": False, "tool_registry": []})

    def to_dict(self) -> dict:
        return asdict(self)
