from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "OpportunityOS"
    database_url: str = "sqlite+pysqlite:///:memory:"
    llm_mode: Literal["mock", "live"] = "mock"
    orchestrator: Literal["local", "crewai"] = "local"

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str | None = None
    anthropic_api_key: str | None = Field(default=None, repr=False)
    anthropic_model: str | None = None

    http_timeout_seconds: float = 15.0
    max_source_bytes: int = 1_000_000
    auto_create_schema: bool = True

    @model_validator(mode="after")
    def validate_live_settings(self) -> Settings:
        if self.llm_mode == "live":
            required = {
                "OPENAI_API_KEY": self.openai_api_key,
                "OPENAI_MODEL": self.openai_model,
                "ANTHROPIC_API_KEY": self.anthropic_api_key,
                "ANTHROPIC_MODEL": self.anthropic_model,
            }
            missing = [key for key, value in required.items() if not value]
            if missing:
                raise ValueError(f"Live LLM mode is missing: {', '.join(missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
