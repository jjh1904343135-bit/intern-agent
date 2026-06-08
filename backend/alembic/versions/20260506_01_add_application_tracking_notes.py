"""add application tracking notes

Revision ID: 20260506_01
Revises: 20260421_01
Create Date: 2026-05-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260506_01"
down_revision = "20260421_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("tracking_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "tracking_notes")
