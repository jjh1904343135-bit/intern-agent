"""Startup bootstrap for the domestic job catalog."""

from __future__ import annotations

from app.scripts.sync_real_jobs import sync_real_jobs


def bootstrap_job_catalog() -> dict:
    """Sync public domestic job sources so a fresh local run has searchable jobs."""
    return sync_real_jobs()
