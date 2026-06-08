from __future__ import annotations

import asyncio
import time
from pathlib import Path

from app.core.database import session_local
from app.core.settings import settings
from app.repositories.resume_repository import ResumeRepository
from app.services.resume_service import ResumeService
from app.tasks.application_tasks import advance_pending_applications_once


def process_pending_resumes_once(limit: int = 10) -> int:
    processed = 0
    with session_local() as db:
        repository = ResumeRepository(db)
        resumes = repository.list_processing(limit=limit)
        for resume in resumes:
            try:
                file_path = Path(resume.file_url)
                service = ResumeService(repository)
                parsed_content = asyncio.run(
                    service.parse_resume_content(file_name=resume.file_name, file_bytes=file_path.read_bytes())
                )
                repository.save_parsed_content_progress(resume=resume, parsed_content=parsed_content)
                score_report = asyncio.run(service.build_score_report(file_name=resume.file_name, parsed_content=parsed_content))
                repository.mark_done(resume=resume, parsed_content=parsed_content, score_report=score_report)
                processed += 1
            except Exception as exc:  # pragma: no cover - keep one bad resume from stopping the worker.
                repository.mark_failed(resume=resume, parse_error=str(exc))
    return processed


def run_worker() -> None:
    while True:
        process_pending_resumes_once()
        advance_pending_applications_once()
        time.sleep(settings.resume_worker_interval_seconds)


if __name__ == "__main__":
    run_worker()
