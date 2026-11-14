from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jobre_env: str = "development"
    jobre_app_name: str = "Jobre"
    jobre_api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://jobre@127.0.0.1:5432/jobre"
    test_database_url: str = "postgresql+psycopg://jobre@127.0.0.1:5432/jobre_test"
    db_pool_size: int = 15
    db_max_overflow: int = 25

    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_enabled: bool = True

    opensearch_enabled: bool = False
    opensearch_url: str = "http://127.0.0.1:9200"
    opensearch_index: str = "jobre_jobs_v1"

    raw_storage_backend: str = "local"
    raw_storage_path: str = str(PROJECT_ROOT / "data" / "raw_snapshots")
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_bucket: str = "jobre-raw-snapshots"
    s3_access_key: str = ""
    s3_secret_key: str = ""

    jobre_admin_api_key: str = "jobre-admin-2026"

    jobre_user_agent: str = "JobreBot/1.0 (+https://github.com/Sanusi-Abdulmalik/jobre)"
    http_timeout_seconds: float = 20.0
    http_max_retries: int = 3
    default_rate_limit_rpm: int = 60
    allow_private_network_urls: bool = False

    dedup_auto_merge_threshold: float = 0.88
    dedup_review_threshold: float = 0.68
    closure_missing_runs_threshold: int = 2

    api_internal_url: str = "http://127.0.0.1:8000"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
