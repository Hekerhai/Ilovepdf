"""Application settings, read from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # General
    brand_name: str = "Folio"
    environment: Literal["development", "test", "production"] = "development"
    public_url: str = "http://localhost:3000"
    secret_key: str = "change-me-in-production"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Infrastructure
    database_url: str = "sqlite:///./folio.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_mode: Literal["rq", "inline"] = "rq"

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: Path = Path("./data/files")
    s3_endpoint_url: str | None = None
    s3_bucket: str = "folio"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"
    work_dir: Path = Path("./data/work")

    # Privacy
    file_ttl_hours: float = 2.0
    esign_retention_days: int = 30  # signed copies are kept this long after completion, then deleted
    webhook_allow_private: bool = False  # let API webhooks reach private/loopback addresses (development only)
    janitor_interval_seconds: int = 300

    # Engines
    gotenberg_url: str | None = None  # e.g. http://gotenberg:3000; falls back to local soffice
    soffice_bin: str = "soffice"
    ghostscript_bin: str = "gs"
    ocr_languages: str = "eng"
    tool_timeout_seconds: int = 600

    # Auth
    access_token_minutes: int = 60 * 24 * 7
    magic_link_minutes: int = 15
    google_client_id: str | None = None
    google_client_secret: str | None = None
    cookie_secure: bool = False

    # Mail
    smtp_host: str | None = None
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    mail_from: str = "Folio <no-reply@folio.local>"

    # Payments
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None

    # AI
    ai_provider: Literal["none", "anthropic", "openai"] = "none"
    ai_api_key: str | None = None
    ai_model: str = "claude-opus-5-5"
    ai_base_url: str | None = None  # for OpenAI-compatible servers (Ollama, vLLM, ...)
    ai_max_input_chars: int = 150_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
