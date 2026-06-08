from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.interview_session_repository import InterviewSessionRepository
from app.repositories.job_repository import JobRepository
from app.repositories.resume_repository import ResumeRepository
from app.schemas.interview import StartInterviewRequest, SubmitInterviewAnswerRequest
from app.services.interview_service import InterviewService, InterviewServiceError
from app.services.streaming import encode_sse_event, stream_event

router = APIRouter(prefix="/api/v1/interview", tags=["interview"])


@router.post("/session/start", status_code=201)
def start_interview_session(
    payload: StartInterviewRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InterviewService(InterviewSessionRepository(db), JobRepository(db), ResumeRepository(db))
    try:
        data = service.start_session(
            user_id=user_id,
            job_id=payload.job_id,
            mode=payload.mode,
            resume_id=payload.resume_id,
            force_new=payload.force_new,
        )
        return {"code": 0, "data": data}
    except InterviewServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/session/{session_id}/answer")
async def submit_interview_answer(
    session_id: str,
    payload: SubmitInterviewAnswerRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InterviewService(InterviewSessionRepository(db), JobRepository(db), ResumeRepository(db))
    try:
        data = await service.submit_answer(user_id=user_id, session_id=session_id, answer=payload.answer)
        return {"code": 0, "data": data}
    except InterviewServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/session/{session_id}/answer/stream")
async def submit_interview_answer_stream(
    session_id: str,
    payload: SubmitInterviewAnswerRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InterviewService(InterviewSessionRepository(db), JobRepository(db), ResumeRepository(db))

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in service.stream_answer_events(user_id=user_id, session_id=session_id, answer=payload.answer):
                yield encode_sse_event(event)
        except InterviewServiceError as exc:
            yield encode_sse_event(
                stream_event(
                    "error",
                    conversation_id=session_id,
                    message_id="",
                    message=exc.message,
                    code=exc.code,
                )
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/session/{session_id}")
def get_interview_session(
    session_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InterviewService(InterviewSessionRepository(db), JobRepository(db), ResumeRepository(db))
    try:
        data = service.get_session(user_id=user_id, session_id=session_id)
        return {"code": 0, "data": data}
    except InterviewServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.get("/sessions")
def list_interview_sessions(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InterviewService(InterviewSessionRepository(db), JobRepository(db), ResumeRepository(db))
    data = service.list_sessions(user_id=user_id)
    return {"code": 0, "data": data}


@router.get("/session/{session_id}/report")
def get_interview_report(
    session_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = InterviewService(InterviewSessionRepository(db), JobRepository(db), ResumeRepository(db))
    try:
        data = service.get_report(user_id=user_id, session_id=session_id)
        return {"code": 0, "data": data}
    except InterviewServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})
