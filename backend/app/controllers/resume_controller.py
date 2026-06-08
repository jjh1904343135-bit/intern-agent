from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.resume_repository import ResumeRepository
from app.services.resume_service import ResumeService, ResumeServiceError

router = APIRouter(prefix="/api/v1/resume", tags=["resume"])


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ResumeService(ResumeRepository(db))
    try:
        data = service.upload_resume(
            user_id=user_id,
            file_name=file.filename or "resume.pdf",
            file_bytes=await file.read(),
        )
        return {"code": 0, "data": data}
    except ResumeServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.get("/{resume_id}/status")
async def get_resume_status(
    resume_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ResumeService(ResumeRepository(db))
    try:
        data = await service.get_status(user_id=user_id, resume_id=resume_id)
        return {"code": 0, "data": data}
    except ResumeServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})
