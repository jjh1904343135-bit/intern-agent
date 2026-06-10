from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "InternAgent API"
    app_env: str = "dev"
    app_port: int = 8000
    llm_provider: str = "mock"

    postgres_db: str = "internagent"
    postgres_user: str = "intern"
    postgres_password: str = "intern123"
    postgres_port: int = 5432
    database_url: str | None = None

    jwt_secret_key: str = "intern-agent-dev-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_seconds: int = 900
    refresh_token_expire_days: int = 7
    resume_storage_dir: str = "/app/runtime/resumes"
    ai_assistant_memory_dir: str = "/app/runtime/ai_assistant_memory"
    resume_worker_interval_seconds: int = 2
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_jobs_collection: str = "jobs"
    qdrant_resumes_collection: str = "resumes"
    qdrant_knowledge_collection: str = "knowledge_chunks"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    embedding_provider: str = "dashscope"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com"
    # Day 7 只预留 Claude 接入位置，当前仍然走规则引擎，不发起外部请求。
    claude_api_key: str | None = None
    claude_base_url: str | None = None
    claude_model: str = "gemma4:26b"
    claude_transport: str = "ollama_generate"
    claude_timeout_seconds: int = 120
    llm_context_window_tokens: int = 8192
    llm_context_compression_ratio: float = 0.5
    llm_context_reserved_output_tokens: int = 900
    chat_llm_planner_enabled: bool = True
    chat_llm_planner_max_tokens: int = 500
    dream_enabled: bool = True
    dream_interval_hours: int = 2
    dream_max_batch_size: int = 20
    dream_max_iterations: int = 15
    dream_model_override: str | None = None
    serpapi_api_key: str | None = None
    apify_token: str | None = None
    enable_global_ats: bool = False
    enable_liepin_mcp: bool = False
    liepin_mcp_url: str | None = None
    liepin_mcp_token: str | None = None
    liepin_mcp_tool_name: str | None = None
    liepin_mcp_queries: str = "产品经理@北京;Java@北京;Java@上海;Java@深圳;后端开发@深圳;前端开发@上海;测试开发@杭州;算法工程师@北京;数据分析@上海;运营@杭州;市场@广州;销售@成都;财务@北京;人力资源@上海"
    liepin_mcp_limit_per_query: int = 10
    liepin_mcp_timeout_seconds: int = 30

    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_allowed_chat_ids: str = ""
    telegram_default_user_email: str | None = None
    telegram_poll_timeout_seconds: int = 0
    telegram_poll_limit: int = 20
    telegram_timezone: str = "Asia/Shanghai"
    telegram_quiet_start_hour: int = 23
    telegram_quiet_end_hour: int = 8
    telegram_daily_push_limit: int = 3
    telegram_same_type_cooldown_hours: int = 12
    telegram_notification_tick_seconds: int = 300
    telegram_bind_code_ttl_minutes: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
