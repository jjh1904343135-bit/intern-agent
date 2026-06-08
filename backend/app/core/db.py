from app.core.settings import settings


# 优先读取 DATABASE_URL，若未配置则自动拼接本地默认连接串。
def build_database_url() -> str:
    if settings.database_url:
        return settings.database_url

    return (
        f"postgresql+psycopg2://{settings.postgres_user}:{settings.postgres_password}"
        f"@postgres:{settings.postgres_port}/{settings.postgres_db}"
    )
