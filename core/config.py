from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAILY_", env_file=".env", extra="ignore")
    poll_interval_seconds: int = 180
    backfill_months: int = 12
    attachment_cache_mb: int = 500
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()
