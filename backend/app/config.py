"""Application configuration loaded from environment variables (.env).

No secrets are hard-coded. Everything is optional and has safe local defaults.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LifePilot"
    environment: str = "development"

    database_url: str = "sqlite:///./lifepilot.db"
    allowed_origins: str = "*"

    # LLM
    llm_provider: str = "mock"  # "mock" | "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    @property
    def origins_list(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
