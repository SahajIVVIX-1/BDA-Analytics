"""Application settings, loaded from environment variables / a `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "social_analytics"
    # Server selection timeout; keeps the API from hanging when MongoDB is down.
    mongo_timeout_ms: int = 5000

    api_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    upload_dir: Path = PROJECT_DIR / "data" / "uploads"
    max_upload_mb: int = 500
    model_dir: Path = BACKEND_DIR / "models"

    # Batch sizes keep memory bounded regardless of dataset size.
    ingest_batch_size: int = 5000
    nlp_batch_size: int = 5000

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
