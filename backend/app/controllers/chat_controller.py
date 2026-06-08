from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.chat_session_repository import ChatSessionRepository
from app.schemas.chat import ChatStreamRequest
from app.services.chat_service import ChatService, ChatServiceError
from app.services.streaming import stream_event

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.get("/sessions")
def list_chat_sessions(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChatService(ChatSessionRepository(db))
    data = service.list_sessions(user_id=user_id)
    return {"code": 0, "data": data}


@router.get("/sessions/{session_id}")
def get_chat_session(
    session_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChatService(ChatSessionRepository(db))
    try:
        data = service.get_session(user_id=user_id, session_id=session_id)
        return {"code": 0, "data": data}
    except ChatServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = ChatService(ChatSessionRepository(db))

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in service.stream_events(
                user_id=user_id,
                message=payload.message,
                session_id=payload.session_id,
                action=payload.action,
            ):
                yield ChatService.encode_sse([event])
        except ChatServiceError as exc:
            error_event = stream_event(
                "error",
                conversation_id=payload.session_id or "",
                message_id="",
                message=exc.message,
                code=exc.code,
            )
            yield ChatService.encode_sse([error_event])

    return StreamingResponse(event_generator(), media_type="text/event-stream")
