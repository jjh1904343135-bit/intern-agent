from app.models import application, chat_session, interview_session, job, knowledge, resume, user  # noqa: F401
from app.models.base import Base


def test_core_tables_exist() -> None:
    expected_tables = {
        "users",
        "resumes",
        "jobs",
        "applications",
        "interview_sessions",
        "chat_sessions",
        "knowledge_documents",
        "knowledge_chunks",
    }
    assert expected_tables.issubset(set(Base.metadata.tables.keys()))


def test_users_key_columns() -> None:
    users = Base.metadata.tables["users"]
    for column_name in ["id", "email", "password_hash", "name", "plan", "profile", "created_at"]:
        assert column_name in users.c


def test_applications_key_columns() -> None:
    applications = Base.metadata.tables["applications"]
    for column_name in ["id", "user_id", "job_id", "resume_id", "status", "status_updated_at"]:
        assert column_name in applications.c
