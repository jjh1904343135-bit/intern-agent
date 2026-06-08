"""widen job fields for real ATS sources

Revision ID: 20260419_02
Revises: 20260419_01
Create Date: 2026-04-19 16:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260419_02"
down_revision: Union[str, Sequence[str], None] = "20260419_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 真实 ATS 的 location / compensation 往往比早期 mock 数据更长。
    """中文注释：用于处理 upgrade 相关后端功能。"""
    op.alter_column("jobs", "city", existing_type=sa.String(length=50), type_=sa.String(length=200), existing_nullable=True)
    op.alter_column("jobs", "salary_range", existing_type=sa.String(length=100), type_=sa.String(length=200), existing_nullable=True)
    op.alter_column("jobs", "duration", existing_type=sa.String(length=50), type_=sa.String(length=100), existing_nullable=True)


def downgrade() -> None:
    """中文注释：用于处理 downgrade 相关后端功能。"""
    op.alter_column("jobs", "duration", existing_type=sa.String(length=100), type_=sa.String(length=50), existing_nullable=True)
    op.alter_column("jobs", "salary_range", existing_type=sa.String(length=200), type_=sa.String(length=100), existing_nullable=True)
    op.alter_column("jobs", "city", existing_type=sa.String(length=200), type_=sa.String(length=50), existing_nullable=True)
