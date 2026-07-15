from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["openai", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "OpportunityOS"
    database_url: str = "sqlite+pysqlite:///:memory:"
    llm_mode: Literal["mock", "live"] = "mock"
    orchestrator: Literal["local", "crewai"] = "local"

    llm_primary_provider: Literal["auto", "openai", "anthropic"] = "auto"
    llm_fallback_enabled: bool = True
    llm_max_calls_per_analysis: int = Field(default=5, ge=2, le=10)
    llm_max_estimated_input_tokens_per_analysis: int = Field(default=18_000, ge=1_000, le=200_000)
    llm_max_output_tokens_per_analysis: int = Field(default=6_000, ge=500, le=50_000)
    llm_max_prompt_chars: int = Field(default=60_000, ge=5_000, le=500_000)
    llm_max_source_chars: int = Field(default=30_000, ge=1_000, le=200_000)
    llm_extraction_max_output_tokens: int = Field(default=1_200, ge=200, le=10_000)
    llm_analysis_max_output_tokens: int = Field(default=1_600, ge=200, le=10_000)
    llm_outreach_max_output_tokens: int = Field(default=900, ge=100, le=5_000)

    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str | None = None
    anthropic_api_key: str | None = Field(default=None, repr=False)
    anthropic_model: str | None = None

    http_timeout_seconds: float = Field(default=30.0, ge=1.0, le=180.0)
    max_source_bytes: int = 1_000_000
    auto_create_schema: bool = True

    @property
    def configured_live_providers(self) -> tuple[ProviderName, ...]:
        providers: list[ProviderName] = []
        if self.openai_api_key and self.openai_model:
            providers.append("openai")
        if self.anthropic_api_key and self.anthropic_model:
            providers.append("anthropic")
        return tuple(providers)

    @model_validator(mode="after")
    def validate_live_settings(self) -> Settings:
        incomplete: list[str] = []
        if bool(self.openai_api_key) != bool(self.openai_model):
            incomplete.append("OpenAI requires both OPENAI_API_KEY and OPENAI_MODEL")
        if bool(self.anthropic_api_key) != bool(self.anthropic_model):
            incomplete.append("Anthropic requires both ANTHROPIC_API_KEY and ANTHROPIC_MODEL")
        if incomplete:
            raise ValueError("; ".join(incomplete))

        if self.llm_max_source_chars > self.llm_max_prompt_chars:
            raise ValueError("LLM_MAX_SOURCE_CHARS cannot exceed LLM_MAX_PROMPT_CHARS")
        minimum_core_output = self.llm_extraction_max_output_tokens + self.llm_analysis_max_output_tokens
        if self.llm_max_output_tokens_per_analysis < minimum_core_output:
            raise ValueError(
                "LLM_MAX_OUTPUT_TOKENS_PER_ANALYSIS must cover extraction and analysis token ceilings"
            )

        if self.llm_mode == "live":
            configured = self.configured_live_providers
            if not configured:
                raise ValueError("Live LLM mode requires at least one complete provider configuration")
            if self.llm_primary_provider != "auto" and self.llm_primary_provider not in configured:
                raise ValueError(
                    f"Primary provider {self.llm_primary_provider} is not fully configured"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
