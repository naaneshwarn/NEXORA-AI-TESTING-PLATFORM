from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="NEXORA")
    app_env: str = Field(default="development")
    api_prefix: str = Field(default="/api/v1")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])


settings = Settings()
