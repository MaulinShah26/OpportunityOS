from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from fastapi import Depends
from sqlalchemy.orm import Session

from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.config import ProviderName, Settings, get_settings
from opportunityos.infrastructure.database import Database, SqlAlchemyStore
from opportunityos.infrastructure.llm.mock import (
    MockBusinessAnalyst,
    MockOpportunityExtractor,
    MockOutreachWriter,
)
from opportunityos.infrastructure.research import InputOnlyResearchProvider, PublicSourceResearchProvider


@lru_cache
def get_database() -> Database:
    settings = get_settings()
    database = Database(settings.database_url)
    if settings.auto_create_schema:
        database.create_schema()
    return database


def get_session() -> Iterator[Session]:
    with get_database().session() as session:
        yield session


def get_store(session: Session = Depends(get_session)) -> SqlAlchemyStore:
    return SqlAlchemyStore(session)


def _provider_order(settings: Settings) -> list[ProviderName]:
    configured = list(settings.configured_live_providers)
    if settings.llm_primary_provider == "auto":
        ordered = configured
    else:
        secondary = [item for item in configured if item != settings.llm_primary_provider]
        ordered = [settings.llm_primary_provider, *secondary]
    return ordered if settings.llm_fallback_enabled else ordered[:1]


@lru_cache
def get_analysis_service() -> AnalyseOpportunityService:
    settings = get_settings()
    if settings.llm_mode == "mock":
        return AnalyseOpportunityService(
            research=InputOnlyResearchProvider(),
            extractor=MockOpportunityExtractor(),
            analyst=MockBusinessAnalyst(),
            outreach_writer=MockOutreachWriter(),
            orchestrator_name=settings.orchestrator,
            model_metadata={"mode": "mock"},
        )

    from opportunityos.infrastructure.llm.anthropic_provider import (
        AnthropicBusinessAnalyst,
        AnthropicOpportunityExtractor,
        AnthropicOutreachWriter,
    )
    from opportunityos.infrastructure.llm.openai_provider import (
        OpenAIBusinessAnalyst,
        OpenAIOpportunityExtractor,
        OpenAIOutreachWriter,
    )
    from opportunityos.infrastructure.llm.runtime import (
        FallbackBusinessAnalyst,
        FallbackOpportunityExtractor,
        FallbackOutreachWriter,
        LiveModelRuntime,
        ProviderCandidate,
    )

    runtime = LiveModelRuntime(
        max_calls=settings.llm_max_calls_per_analysis,
        max_estimated_input_tokens=settings.llm_max_estimated_input_tokens_per_analysis,
        max_output_tokens=settings.llm_max_output_tokens_per_analysis,
    )
    order = _provider_order(settings)
    extractors: list[ProviderCandidate[Any]] = []
    analysts: list[ProviderCandidate[Any]] = []
    writers: list[ProviderCandidate[Any]] = []

    for provider in order:
        common: dict[str, Any] = {
            "runtime": runtime,
            "timeout_seconds": settings.http_timeout_seconds,
            "max_prompt_chars": settings.llm_max_prompt_chars,
        }
        if provider == "openai":
            common.update(
                api_key=settings.openai_api_key or "",
                model=settings.openai_model or "",
            )
            extractors.append(
                ProviderCandidate(
                    "openai",
                    OpenAIOpportunityExtractor(
                        **common,
                        max_output_tokens=settings.llm_extraction_max_output_tokens,
                        max_source_chars=settings.llm_max_source_chars,
                    ),
                )
            )
            analysts.append(
                ProviderCandidate(
                    "openai",
                    OpenAIBusinessAnalyst(
                        **common,
                        max_output_tokens=settings.llm_analysis_max_output_tokens,
                    ),
                )
            )
            writers.append(
                ProviderCandidate(
                    "openai",
                    OpenAIOutreachWriter(
                        **common,
                        max_output_tokens=settings.llm_outreach_max_output_tokens,
                    ),
                )
            )
        else:
            common.update(
                api_key=settings.anthropic_api_key or "",
                model=settings.anthropic_model or "",
            )
            extractors.append(
                ProviderCandidate(
                    "anthropic",
                    AnthropicOpportunityExtractor(
                        **common,
                        max_output_tokens=settings.llm_extraction_max_output_tokens,
                        max_source_chars=settings.llm_max_source_chars,
                    ),
                )
            )
            analysts.append(
                ProviderCandidate(
                    "anthropic",
                    AnthropicBusinessAnalyst(
                        **common,
                        max_output_tokens=settings.llm_analysis_max_output_tokens,
                    ),
                )
            )
            writers.append(
                ProviderCandidate(
                    "anthropic",
                    AnthropicOutreachWriter(
                        **common,
                        max_output_tokens=settings.llm_outreach_max_output_tokens,
                    ),
                )
            )

    return AnalyseOpportunityService(
        research=PublicSourceResearchProvider(
            timeout_seconds=settings.http_timeout_seconds,
            max_source_bytes=settings.max_source_bytes,
        ),
        extractor=FallbackOpportunityExtractor(extractors),
        analyst=FallbackBusinessAnalyst(analysts),
        outreach_writer=FallbackOutreachWriter(writers),
        orchestrator_name=settings.orchestrator,
        model_runtime=runtime,
        model_metadata={
            "mode": "live",
            "provider_order": ",".join(order),
            "fallback_enabled": str(settings.llm_fallback_enabled).lower(),
            "openai_model": settings.openai_model or "",
            "anthropic_model": settings.anthropic_model or "",
        },
    )
