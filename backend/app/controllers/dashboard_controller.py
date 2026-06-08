from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.dashboard_repository import DashboardRepository
from app.services.dashboard_service import DashboardService, DashboardServiceError

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    service = DashboardService(DashboardRepository(db))
    try:
        data = service.get_summary(user_id=user_id)
        return {"code": 0, "data": data}
    except DashboardServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})
