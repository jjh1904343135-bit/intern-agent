from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest
from app.services.auth_service import AuthService, AuthServiceError

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    service = AuthService(UserRepository(db))
    try:
        data = service.register(email=payload.email, password=payload.password, name=payload.name)
        return {"code": 0, "data": data}
    except AuthServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/login", status_code=200)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    service = AuthService(UserRepository(db))
    try:
        data = service.login(email=payload.email, password=payload.password)
        return {"code": 0, "data": data}
    except AuthServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})


@router.post("/refresh", status_code=200)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    service = AuthService(UserRepository(db))
    try:
        data = service.refresh_access_token(refresh_token=payload.refresh_token)
        return {"code": 0, "data": data}
    except AuthServiceError as exc:
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message})