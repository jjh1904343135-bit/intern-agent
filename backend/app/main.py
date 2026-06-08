"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.controllers.application_controller import router as application_router
from app.controllers.auth_controller import router as auth_router
from app.controllers.chat_controller import router as chat_router
from app.controllers.dashboard_controller import router as dashboard_router
from app.controllers.health_controller import router as health_router
from app.controllers.interview_controller import router as interview_router
from app.controllers.job_controller import router as job_router
from app.controllers.resume_controller import router as resume_router
from app.controllers.scheduled_task_controller import router as scheduled_task_router
from app.controllers.telegram_controller import router as telegram_router
from app.core.database import session_local
from app.core.settings import settings
from app.scripts.bootstrap_jobs import bootstrap_job_catalog
from app.scripts.reindex_embeddings import rebuild_search_indexes
from app.scripts.seed_default_user import ensure_default_admin_user


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Bootstrap local data before serving requests."""
    with session_local() as db:
        ensure_default_admin_user(db)

    # 国内岗位目录是岗位页的最低可用保障，必须在启动时同步。
    bootstrap_job_catalog()

    try:
        rebuild_search_indexes()
    except Exception:
        # 索引失败不阻断 API，岗位列表仍可从 PostgreSQL 搜索。
        pass
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(job_router)
app.include_router(resume_router)
app.include_router(application_router)
app.include_router(interview_router)
app.include_router(chat_router)
app.include_router(telegram_router)
app.include_router(scheduled_task_router)
