"""
Typed application configuration.

All configuration is sourced from environment variables (see .env.example at
the repo root). Nothing here should ever contain a hard-coded secret — only
safe local-development defaults that are meant to be overridden in real
deployments.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "GST AI Copilot"
    app_debug: bool = True
    app_secret_key: str = Field(default="dev-secret-change-me")
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    service_role: Literal["api", "worker", "beat"] = "api"

    # ---- PostgreSQL ----
    database_url: str = "postgresql+asyncpg://gst_copilot:gst_copilot_pw@localhost:5432/gst_copilot"
    database_url_sync: str = (
        "postgresql+psycopg://gst_copilot:gst_copilot_pw@localhost:5432/gst_copilot"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- Qdrant ----
    # Set qdrant_local_path to run an embedded, on-disk Qdrant (no server /
    # cloud cluster needed) — for local development / CI. When it's set,
    # qdrant_url is ignored. Embedded mode is single-process only.
    qdrant_url: str = "http://localhost:6333"
    qdrant_local_path: str | None = None
    qdrant_api_key: str | None = None
    qdrant_prefer_grpc: bool = False

    # ---- Object storage (MinIO / S3-compatible) ----
    # "minio" talks to an S3-compatible service at object_storage_endpoint.
    # "filesystem" stores objects as plain files under
    # object_storage_filesystem_root — no external service needed, for local
    # development / CI.
    object_storage_provider: Literal["minio", "filesystem"] = "minio"
    object_storage_filesystem_root: str = ".data/object-storage"
    object_storage_endpoint: str = "localhost:9000"
    object_storage_access_key: str = "gst_copilot_admin"
    object_storage_secret_key: str = "change-me-minio-secret"
    object_storage_secure: bool = False
    object_storage_region: str = "us-east-1"
    object_storage_bucket_documents: str = "gst-documents"
    object_storage_bucket_invoices: str = "invoices"
    object_storage_bucket_supporting: str = "supporting-documents"
    object_storage_bucket_knowledge: str = "knowledge-documents"
    object_storage_bucket_exports: str = "exports"
    object_storage_bucket_backups: str = "backups"

    # ---- LLM ----
    llm_provider: Literal["ollama", "openai", "azure_openai", "anthropic"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    # Set to use Ollama Cloud (https://ollama.com) instead of a local/
    # self-hosted server — sent as `Authorization: Bearer <key>`. Leave
    # unset for a local Ollama install, which needs no auth.
    ollama_api_key: str | None = None
    ollama_model: str = "qwen2.5:7b-instruct"
    ollama_temperature: float = 0.1
    ollama_timeout: int = 120
    ollama_num_ctx: int = 8192
    chat_request_timeout_seconds: int = 45

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    # ---- Embeddings ----
    embedding_provider: Literal["fastembed", "ollama"] = "fastembed"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    embedding_batch_size: int = 32

    # ---- Reranker ----
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_top_k: int = 8

    # ---- OCR ----
    ocr_provider: Literal["paddleocr", "tesseract"] = "tesseract"
    ocr_language: str = "en"
    tesseract_cmd: str | None = None

    # ---- Celery ----
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_task_always_eager: bool = False

    # ---- Auth / JWT ----
    jwt_secret: str = "change-me-jwt-secret-must-be-long-and-random"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 14

    # ---- Rate limiting ----
    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"

    # ---- Uploads ----
    max_upload_size_mb: int = 25
    allowed_upload_extensions: str = "pdf,png,jpg,jpeg,tiff,docx,xlsx,csv,txt,json"

    # ---- Observability ----
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "gst-ai-copilot-api"
    prometheus_enabled: bool = True
    langchain_tracing_v2: bool = False
    langchain_api_key: str | None = None
    langchain_project: str = "gst-ai-copilot"

    # ---- GST rule engine ----
    gst_rules_version: str = "2026.01"
    gst_rounding_mode: str = "ROUND_HALF_UP"

    @field_validator("allowed_upload_extensions")
    @classmethod
    def _normalize_extensions(cls, v: str) -> str:
        return v.lower().replace(" ", "")

    @property
    def allowed_upload_extensions_list(self) -> list[str]:
        return [e for e in self.allowed_upload_extensions.split(",") if e]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env is read once per process)."""
    return Settings()
