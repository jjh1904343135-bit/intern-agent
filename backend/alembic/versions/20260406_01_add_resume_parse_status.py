"""add resume parse status

Revision ID: 20260406_01
Revises: 20260329_01
Create Date: 2026-04-06 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260406_01"
down_revision: Union[str, Sequence[str], None] = "20260329_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 中文注释：Day 4 需要显式记录解析状态，方便轮询 worker 和状态查询接口复用。
    """中文注释：用于处理 upgrade 相关后端功能。"""
    op.add_column("resumes", sa.Column("parse_status", sa.String(length=32), nullable=False, server_default="processing"))
    op.add_column("resumes", sa.Column("parse_error", sa.Text(), nullable=True))


def downgrade() -> None:
    """中文注释：用于处理 downgrade 相关后端功能。"""
    op.drop_column("resumes", "parse_error")
    op.drop_column("resumes", "parse_status")
