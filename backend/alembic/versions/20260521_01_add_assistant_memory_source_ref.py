"""add assistant memory source ref

Revision ID: 20260521_01
Revises: 20260509_02
Create Date: 2026-05-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260521_01"
down_revision = "20260509_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_memories",
        sa.Column("source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("assistant_memories", "source_ref")
