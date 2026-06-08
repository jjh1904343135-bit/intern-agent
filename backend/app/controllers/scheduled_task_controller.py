from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.scheduled_task_repository import ScheduledTaskRepository
from app.schemas.scheduled_task import UpdateScheduledTaskRequest
from app.services.scheduled_task_service import ScheduledTaskService

router = APIRouter(prefix="/api/v1", tags=["scheduled-tasks"])


def _service(db: Session) -> ScheduledTaskService:
    return ScheduledTaskService(repository=ScheduledTaskRepository(db))


@router.get("/scheduled-tasks")
def list_scheduled_tasks(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return {"code": 0, "data": _service(db).list_tasks(user_id=user_id)}


@router.patch("/scheduled-tasks/{task_id}")
def update_scheduled_task(
    task_id: str,
    payload: UpdateScheduledTaskRequest,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    data = _service(db).update_task_status(user_id=user_id, task_id=task_id, status=payload.status)
    if data is None:
        return JSONResponse(status_code=404, content={"code": 6404, "message": "Scheduled task not found"})
    return {"code": 0, "data": data}


@router.get("/scheduled-tasks/{task_id}/runs")
def list_scheduled_task_runs(
    task_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return {"code": 0, "data": _service(db).list_runs(user_id=user_id, task_id=task_id)}


@router.get("/task-inbox")
def list_task_inbox(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    return {"code": 0, "data": _service(db).list_inbox(user_id=user_id)}


@router.patch("/task-inbox/{inbox_id}/read")
def mark_task_inbox_read(
    inbox_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    data = _service(db).mark_inbox_read(user_id=user_id, inbox_id=inbox_id)
    if data is None:
        return JSONResponse(status_code=404, content={"code": 6405, "message": "Task inbox item not found"})
    return {"code": 0, "data": data}
