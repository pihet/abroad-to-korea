from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str | None = None
    redis_url: str | None = None
    public_base_url: str = "http://localhost:8000"
    cookie_secure: bool = False

    resend_api_key: str | None = None
    resend_from_email: str = "Abroad to Korea <onboarding@resend.dev>"
    resend_reply_to: str | None = None
    email_worker_poll_seconds: float = 2.0

    google_client_id: str | None = None
    google_client_secret: str | None = None
    kakao_client_id: str | None = None
    kakao_client_secret: str | None = None

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin-change-me"
    minio_secure: bool = False
    minio_bucket: str = "abroad-to-korea"


@lru_cache
def get_settings() -> Settings:
    return Settings()
