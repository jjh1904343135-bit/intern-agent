"""中文注释：后端模块，包含 alembic/env.py 相关功能，数据库迁移脚本，负责记录表结构变更。"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.db import build_database_url
from app.models.base import Base
from app.models import application, chat_session, interview_session, job, knowledge, resume, user  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", build_database_url())

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """中文注释：用于同步或处理 run_migrations_offline 相关后端功能。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """中文注释：用于同步或处理 run_migrations_online 相关后端功能。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
