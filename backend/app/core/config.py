from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """AI 智能客服系统统一配置。"""

    # Application
    app_name: str = "AI Customer Service API"
    app_version: str = "0.1.0"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    frontend_origin: str = "http://127.0.0.1:5173"

    # MySQL
    mysql_host: str = "127.0.0.1"
    mysql_port: Annotated[int, Field(ge=1, le=65535)] = 3306
    mysql_user: str = "ai_customer_service"
    mysql_password: str = "CHANGE_ME"
    mysql_database: str = "ai_customer_service"
    mysql_charset: str = "utf8mb4"

    # Authentication
    jwt_secret_key: str = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: Annotated[int, Field(gt=0)] = 120

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_chat_model: str = "qwen3.5:4b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_embedding_dimension: Annotated[int, Field(gt=0)] = 1024
    ollama_request_timeout_seconds: Annotated[int, Field(gt=0)] = 300
    ollama_num_ctx: Annotated[int, Field(ge=1024)] = 4096
    ollama_retry_attempts: Annotated[int, Field(ge=1, le=5)] = 3
    ollama_retry_backoff_seconds: Annotated[
        float,
        Field(ge=0.0, le=10.0),
    ] = 0.25

    # Chroma
    chroma_persist_dir: Path = Path("storage/chroma")
    chroma_collection_prefix: str = "ai_customer_service"

    # Uploads
    upload_dir: Path = Path("storage/uploads")
    max_upload_size_mb: Annotated[int, Field(gt=0)] = 20
    allowed_document_extensions: Annotated[tuple[str, ...], NoDecode] = (".txt", ".md", ".pdf")
    chunk_size: Annotated[int, Field(ge=200)] = 800
    chunk_overlap: Annotated[int, Field(ge=0)] = 120

    # Chat and RAG
    question_max_length: Annotated[int, Field(gt=0)] = 500
    daily_question_limit: Annotated[int, Field(gt=0)] = 100
    context_history_rounds: Annotated[int, Field(ge=0)] = 6
    rag_top_k: Annotated[int, Field(gt=0)] = 5
    rag_similarity_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.55
    # 多知识库自动路由：先跨库探测，再只在最相关知识库内做最终 Top-K。
    rag_route_probe_top_k: Annotated[int, Field(gt=0)] = 20
    rag_route_similarity_threshold: Annotated[
        float,
        Field(ge=0.0, le=1.0),
    ] = 0.35
    rag_max_context_chars: Annotated[int, Field(gt=0)] = 12000
    # Large-context evidence governance.
    rag_max_sources: Annotated[int, Field(ge=1, le=50)] = 8
    rag_max_chunks_per_document: Annotated[int, Field(ge=1, le=10)] = 2
    rag_critical_priority: Annotated[int, Field(ge=0)] = 5
    rag_critical_source_limit: Annotated[int, Field(ge=1, le=20)] = 4
    rag_rule_sentences_per_source: Annotated[int, Field(ge=1, le=10)] = 3
    rag_support_sentences_per_source: Annotated[int, Field(ge=1, le=10)] = 2
    rag_answer_guard_enabled: bool = True
    rag_answer_repair_attempts: Annotated[int, Field(ge=0, le=2)] = 1
    follow_up_suggestion_count: Annotated[int, Field(ge=2, le=3)] = 3
    empty_retrieval_reply: str = (
        "抱歉，当前知识库中没有找到能够可靠回答该问题的相关信息。"
        "请换一种方式提问，或联系人工客服进一步确认。"
    )

    # AI Agent task planning.
    agent_requirement_max_chars: Annotated[int, Field(ge=100, le=20000)] = 4000
    agent_system_context_max_chars: Annotated[int, Field(ge=1000, le=100000)] = 24000
    agent_max_services: Annotated[int, Field(ge=1, le=30)] = 12
    agent_max_tasks: Annotated[int, Field(ge=1, le=100)] = 30
    agent_planner_temperature: Annotated[float, Field(ge=0.0, le=1.0)] = 0.1
    agent_planner_repair_attempts: Annotated[int, Field(ge=0, le=2)] = 2

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("allowed_document_extensions", mode="before")
    @classmethod
    def parse_extensions(cls, value: object) -> object:
        """支持从逗号分隔的环境变量读取扩展名列表。"""
        if isinstance(value, str):
            return tuple(
                item.strip().lower()
                for item in value.split(",")
                if item.strip()
            )
        return value

    @field_validator("chroma_persist_dir", "upload_dir", mode="after")
    @classmethod
    def resolve_backend_path(cls, value: Path) -> Path:
        """将相对存储路径固定解析到 backend 目录。"""
        if value.is_absolute():
            return value
        return (BACKEND_ROOT / value).resolve()

    @property
    def mysql_safe_dsn(self) -> str:
        """返回不包含密码的 MySQL 连接信息，仅用于日志和检查。"""
        return (
            f"mysql+pymysql://{self.mysql_user}:***@"
            f"{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset={self.mysql_charset}"
        )


@lru_cache
def get_settings() -> Settings:
    """返回全局缓存配置。"""
    return Settings()
