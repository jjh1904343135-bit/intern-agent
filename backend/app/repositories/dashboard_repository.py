from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.application_repository import ApplicationRepository
from app.repositories.chat_session_repository import ChatSessionRepository
from app.repositories.interview_session_repository import InterviewSessionRepository
from app.repositories.resume_repository import ResumeRepository


class DashboardRepository:
    def __init__(self, db: Session):
        self.db = db
        self.resume_repository = ResumeRepository(db)
        self.application_repository = ApplicationRepository(db)
        self.interview_repository = InterviewSessionRepository(db)
        self.chat_repository = ChatSessionRepository(db)

    def get_dashboard_snapshot(self, *, user_id: str) -> dict:
        applications = self.application_repository.list_by_user_id(user_id=user_id)
        interviews = self.interview_repository.list_by_user_id(user_id=user_id, limit=5)
        chats = self.chat_repository.list_by_user_id(user_id=user_id, limit=5)
        latest_resume = self.resume_repository.get_latest_by_user_id(user_id=user_id)

        return {
            "latest_resume": latest_resume,
            "resume_count": self.resume_repository.count_by_user_id(user_id=user_id),
            "applications": applications,
            "interviews": interviews,
            "interview_total": self.interview_repository.count_by_user_id(user_id=user_id),
            "chats": chats,
            "chat_total": self.chat_repository.count_by_user_id(user_id=user_id),
        }
