from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import bearer_scheme, resolve_current_user_id
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository
from app.services.job_service import JobService, JobServiceError

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/search")
def search_jobs(
    keyword: str | None = Query(default=None),
    city: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    match_resume: bool = Query(default=False),
    db: Session = Depends(get_db),
    credentials=Depends(bearer_scheme),
):
    service = JobService(JobRepository(db), ResumeRepository(db))
    user_id = None

    if credentials is not None:
        try:
            user_id = resolve_current_user_id(credentials, db)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"code": 3001, "message": exc.detail})

    try:
        data = service.search_jobs(
            user_id=user_id,
            match_resume=match_resume,
            keyword=keyword,
            city=city,
            limit=limit,
        )
        return {"code": 0, "data": data}
    except JobServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.get("/discover")
def discover_jobs(
    keyword: str | None = Query(default=None),
    city: str | None = Query(default=None),
    experience: str | None = Query(default=None),
    skills: str | None = Query(default=None, description="Comma-separated skills, e.g. SQL,Python"),
    match_resume: bool = Query(default=False),
    db: Session = Depends(get_db),
    credentials=Depends(bearer_scheme),
):
    service = JobService(JobRepository(db), ResumeRepository(db))
    user_id = None

    if credentials is not None:
        try:
            user_id = resolve_current_user_id(credentials, db)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"code": 3001, "message": exc.detail})

    parsed_skills = tuple(item.strip() for item in (skills or "").split(",") if item.strip())
    try:
        data = service.discover_jobs(
            user_id=user_id,
            match_resume=match_resume,
            keyword=keyword,
            city=city,
            experience=experience,
            skills=parsed_skills,
        )
        return {"code": 0, "data": data}
    except JobServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.get("/{job_id}")
def get_job_detail(
    job_id: str,
    db: Session = Depends(get_db),
):
    service = JobService(JobRepository(db), ResumeRepository(db))
    try:
        data = service.get_job_detail(job_id=job_id)
        return {"code": 0, "data": data}
    except JobServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})
