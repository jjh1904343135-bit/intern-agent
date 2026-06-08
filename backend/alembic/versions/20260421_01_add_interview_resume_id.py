"""bind interview sessions to resumes

Revision ID: 20260421_01
Revises: 20260419_02
Create Date: 2026-04-21 11:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260421_01"
down_revision: Union[str, Sequence[str], None] = "20260419_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """中文注释：用于处理 upgrade 相关后端功能。"""
    op.add_column("interview_sessions", sa.Column("resume_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_interview_sessions_resume_id_resumes",
        "interview_sessions",
        "resumes",
        ["resume_id"],
        ["id"],
    )


def downgrade() -> None:
    """中文注释：用于处理 downgrade 相关后端功能。"""
    op.drop_constraint("fk_interview_sessions_resume_id_resumes", "interview_sessions", type_="foreignkey")
    op.drop_column("interview_sessions", "resume_id")
