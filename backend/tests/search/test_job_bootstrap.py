from __future__ import annotations

import asyncio

from app import main


class _DummySession:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, traceback):
        return False


def test_lifespan_bootstraps_real_job_catalog_before_reindex(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(main, "session_local", lambda: _DummySession())
    monkeypatch.setattr(main, "ensure_default_admin_user", lambda db: calls.append("admin"))
    monkeypatch.setattr(main, "bootstrap_job_catalog", lambda: calls.append("jobs"))
    monkeypatch.setattr(main, "rebuild_search_indexes", lambda: calls.append("index"))

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())

    assert calls == ["admin", "jobs", "index"]
