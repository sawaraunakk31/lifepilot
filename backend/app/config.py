"""Application configuration loaded from environment variables (.env).

Supports multiple free LLM providers, web scraping, ChromaDB vector store,
and optional search APIs. Every setting has a safe default so the app runs
with zero configuration (offline mock mode).
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LifePilot"
    environment: str = "development"

    database_url: str = "sqlite:///./lifepilot.db"
    allowed_origins: str = "http://127.0.0.1:8000,http://localhost:8000"

    # ── LLM ──────────────────────────────────────────────────
    # Providers: "groq" | "gemini" | "ollama" | "mock"
    llm_provider: str = "groq"

    # Groq (free tier — 30 req/min, Llama 3.3 70B)
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.6-27b"

    # Google Gemini (free tier — 15 req/min)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # Local Ollama (unlimited, offline)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    # ── Web Scraping ─────────────────────────────────────────
    scraping_enabled: bool = True
    scraping_cache_hours: int = 24
    serper_api_key: str = ""  # optional — serper.dev free tier (2500 searches)

    # ── ChromaDB ─────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_data"

    @property
    def origins_list(self) -> list[str]:
        if self.allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def has_llm(self) -> bool:
        """True if a real LLM provider is configured (not mock)."""
        if self.llm_provider == "groq" and self.groq_api_key:
            return True
        if self.llm_provider == "gemini" and self.gemini_api_key:
            return True
        if self.llm_provider == "ollama":
            return True
        return False


settings = Settings()
