from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.application_repository import ApplicationRepository
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.application import CreateApplicationRequest, UpdateApplicationNotesRequest
from app.services.application_service import ApplicationService, ApplicationServiceError

router = APIRouter(prefix="/api/v1", tags=["applications"])


def _service(db: Session) -> ApplicationService:
    return ApplicationService(ApplicationRepository(db), JobRepository(db), ResumeRepository(db))


@router.post("/jobs/{job_id}/apply", status_code=201)
def apply_to_job(
    job_id: str,
    payload: CreateApplicationRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = _service(db)
    try:
        data = service.create_application(user_id=user_id, job_id=job_id, cover_letter=payload.cover_letter)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/applications/{application_id}/mark-opened")
def mark_application_opened(
    application_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = _service(db)
    try:
        data = service.mark_opened(user_id=user_id, application_id=application_id)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/applications/{application_id}/mark-applied")
def mark_application_applied(
    application_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = _service(db)
    try:
        data = service.mark_applied(user_id=user_id, application_id=application_id)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/applications/{application_id}/mark-waiting-feedback")
def mark_application_waiting_feedback(
    application_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Mark an application as waiting for employer feedback."""
    service = _service(db)
    try:
        data = service.mark_waiting_feedback(user_id=user_id, application_id=application_id)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/applications/{application_id}/mark-interviewing")
def mark_application_interviewing(
    application_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Mark an application as being in the interview stage."""
    service = _service(db)
    try:
        data = service.mark_interviewing(user_id=user_id, application_id=application_id)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/applications/{application_id}/mark-closed")
def mark_application_closed(
    application_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Close an application workflow."""
    service = _service(db)
    try:
        data = service.mark_closed(user_id=user_id, application_id=application_id)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.patch("/applications/{application_id}/notes")
def update_application_notes(
    application_id: str,
    payload: UpdateApplicationNotesRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Update manual notes such as platform, date, HR contact and feedback."""
    service = _service(db)
    try:
        data = service.update_notes(user_id=user_id, application_id=application_id, tracking_notes=payload.model_dump())
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.get("/applications")
def list_applications(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = _service(db)
    try:
        data = service.list_applications(user_id=user_id)
        return {"code": 0, "data": data}
    except ApplicationServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})
