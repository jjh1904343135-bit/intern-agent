from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import build_database_url


# 统一在这里管理数据库连接与会话，避免在业务代码中重复创建引擎。
engine = create_engine(build_database_url(), pool_pre_ping=True, future=True)
session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Session:
    db = session_local()
    try:
        yield db
    finally:
        db.close()