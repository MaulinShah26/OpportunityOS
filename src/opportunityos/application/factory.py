from __future__ import annotations

from typing import Any

from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.config import ProviderName, Settings
from opportunityos.infrastructure.llm.mock import (
    MockBusinessAnalyst,
    MockOpportunityExtractor,
    MockOutreachWriter,
)
from opportunityos.infrastructure.research import InputOnlyResearchProvider, PublicSourceResearchProvider


def provider_order(settings: Settings) -> list[ProviderName]:
    configured = list(settings.configured_live_providers)
    if settings.llm_primary_provider == "auto":
        ordered = configured
    else:
        secondary = [item for item in configured if item != settings.llm_primary_provider]
        ordered = [settings.llm_primary_provider, *secondary]
    return ordered if settings.llm_fallback_enabled else ordered[:1]


def build_analysis_service(settings: Settings) -> AnalyseOpportunityService:
    """Create one configured analysis service for API, evaluation, or batch use."""
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
    order = provider_order(settings)
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
            common.update(api_key=settings.openai_api_key or "", model=settings.openai_model or "")
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
            continue

        common.update(api_key=settings.anthropic_api_key or "", model=settings.anthropic_model or "")
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
