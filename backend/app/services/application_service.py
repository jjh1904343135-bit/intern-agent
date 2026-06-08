from __future__ import annotations

from dataclasses import dataclass

from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository


@dataclass
class ApplicationServiceError(Exception):
    status_code: int
    code: int
    message: str


class ApplicationService:
    STATUS_FLOW = ["saved", "opened", "applied_manual", "waiting_feedback", "interviewing", "closed"]
    STATUS_TIMELINE = {
        "saved": ["saved"],
        "opened": ["saved", "opened"],
        "applied_manual": ["saved", "opened", "applied_manual"],
        "waiting_feedback": ["saved", "opened", "applied_manual", "waiting_feedback"],
        "interviewing": ["saved", "opened", "applied_manual", "waiting_feedback", "interviewing"],
        "closed": ["saved", "opened", "applied_manual", "waiting_feedback", "interviewing", "closed"],
        "interview_invited": ["saved", "opened", "applied_manual", "interview_invited"],
        "rejected": ["saved", "opened", "applied_manual", "rejected"],
        "offer_received": ["saved", "opened", "applied_manual", "offer_received"],
        "accepted": ["saved", "opened", "applied_manual", "offer_received", "accepted"],
        "declined": ["saved", "opened", "applied_manual", "offer_received", "declined"],
    }

    def __init__(
        self,
        application_repository: ApplicationRepository,
        job_repository: JobRepository,
        resume_repository: ResumeRepository,
    ):
        self.application_repository = application_repository
        self.job_repository = job_repository
        self.resume_repository = resume_repository

    def create_application(self, *, user_id: str, job_id: str, cover_letter: str | None = None) -> dict:
        existing = self.application_repository.get_by_user_and_job(user_id=user_id, job_id=job_id)
        if existing is not None:
            raise ApplicationServiceError(status_code=409, code=4001, message="Application already exists")

        job = self.job_repository.get_by_id(job_id=job_id)
        if job is None or not job.is_active:
            raise ApplicationServiceError(status_code=404, code=4002, message="Job not found")

        resume = self.resume_repository.get_default_by_user_id(user_id=user_id)
        if resume is None or resume.parse_status != "done":
            raise ApplicationServiceError(status_code=400, code=4003, message="Default parsed resume is required")

        application = self.application_repository.create(
            user_id=user_id,
            job_id=job_id,
            resume_id=str(resume.id),
            cover_letter=cover_letter,
        )
        return self._serialize_item(application=application, job=job)

    def mark_opened(self, *, user_id: str, application_id: str) -> dict:
        return self._advance_manual(user_id=user_id, application_id=application_id, allowed={"saved"}, next_status="opened")

    def mark_applied(self, *, user_id: str, application_id: str) -> dict:
        return self._advance_manual(user_id=user_id, application_id=application_id, allowed={"saved", "opened"}, next_status="applied_manual")

    def mark_waiting_feedback(self, *, user_id: str, application_id: str) -> dict:
        """Move an application into the post-submit waiting state."""
        return self._advance_manual(
            user_id=user_id,
            application_id=application_id,
            allowed={"applied_manual", "submitted"},
            next_status="waiting_feedback",
        )

    def mark_interviewing(self, *, user_id: str, application_id: str) -> dict:
        """Mark that the application has entered interview follow-up."""
        return self._advance_manual(
            user_id=user_id,
            application_id=application_id,
            allowed={"applied_manual", "waiting_feedback", "interview_invited"},
            next_status="interviewing",
        )

    def mark_closed(self, *, user_id: str, application_id: str) -> dict:
        """Close an application workflow when the opportunity is no longer active."""
        return self._advance_manual(
            user_id=user_id,
            application_id=application_id,
            allowed=set(self.STATUS_TIMELINE.keys()),
            next_status="closed",
        )

    def update_notes(self, *, user_id: str, application_id: str, tracking_notes: dict) -> dict:
        """Store manual platform/date/contact/feedback notes for a saved application."""
        application = self.application_repository.get_by_id(application_id=application_id, user_id=user_id)
        if application is None:
            raise ApplicationServiceError(status_code=404, code=4004, message="Application not found")
        cleaned = {key: value for key, value in tracking_notes.items() if value not in (None, "")}
        application = self.application_repository.update_tracking_notes(application=application, tracking_notes=cleaned)
        job = self.job_repository.get_by_id(job_id=str(application.job_id))
        return self._serialize_item(application=application, job=job)

    def _advance_manual(self, *, user_id: str, application_id: str, allowed: set[str], next_status: str) -> dict:
        application = self.application_repository.get_by_id(application_id=application_id, user_id=user_id)
        if application is None:
            raise ApplicationServiceError(status_code=404, code=4004, message="Application not found")
        if application.status not in allowed and application.status != next_status:
            raise ApplicationServiceError(status_code=409, code=4005, message="Application status cannot be changed this way")
        if application.status != next_status:
            application = self.application_repository.advance_status(application=application, next_status=next_status)
        job = self.job_repository.get_by_id(job_id=str(application.job_id))
        return self._serialize_item(application=application, job=job)

    def list_applications(self, *, user_id: str) -> dict:
        applications = self.application_repository.list_by_user_id(user_id=user_id)
        job_ids = [str(item.job_id) for item in applications]
        jobs = {str(job.id): job for job in self.job_repository.get_by_ids(job_ids)}
        items = [self._serialize_item(application=item, job=jobs.get(str(item.job_id))) for item in applications]
        return {"total": len(items), "items": items}

    def _serialize_item(self, *, application, job) -> dict:
        timeline = self.STATUS_TIMELINE.get(application.status, [application.status])
        return {
            "application_id": str(application.id),
            "job_id": str(application.job_id),
            "resume_id": str(application.resume_id),
            "status": application.status,
            "timeline": timeline,
            "status_flow": self.STATUS_FLOW,
            "tracking_notes": application.tracking_notes or {},
            "status_updated_at": application.status_updated_at.isoformat() if application.status_updated_at else None,
            "applied_at": application.applied_at.isoformat() if application.applied_at else None,
            "job": {
                "title": job.title if job is not None else None,
                "company": job.company if job is not None else None,
                "city": job.city if job is not None else None,
                "apply_url": job.apply_url if job is not None else None,
                "source": job.source if job is not None else None,
            },
        }
