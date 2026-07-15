from __future__ import annotations

import pytest

from opportunityos.config import Settings
from opportunityos.domain.enums import OpportunityType
from opportunityos.domain.models import EvidenceClaim, OpportunityInput, OpportunityProfile
from opportunityos.infrastructure.llm.runtime import (
    FallbackOpportunityExtractor,
    LiveModelBudgetExceeded,
    LiveModelRuntime,
    ProviderCandidate,
)


class _FailingExtractor:
    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile:
        raise ValueError("invalid provider output")


class _WorkingExtractor:
    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile:
        return OpportunityProfile(
            company_name=source.company_hint or "Test company",
            title="Product Manager",
            opportunity_type=OpportunityType.CONSULTING,
            evidence=evidence,
            extraction_confidence=0.8,
        )


def test_runtime_blocks_calls_before_exceeding_budget() -> None:
    runtime = LiveModelRuntime(
        max_calls=2,
        max_estimated_input_tokens=100,
        max_output_tokens=500,
    )
    runtime.start_run()
    runtime.before_call("openai", "extraction", "short prompt", 200)
    runtime.before_call("anthropic", "analysis", "another short prompt", 200)

    with pytest.raises(LiveModelBudgetExceeded, match="call limit"):
        runtime.before_call("openai", "outreach", "third prompt", 100)


def test_runtime_blocks_large_prompts_before_provider_execution() -> None:
    runtime = LiveModelRuntime(
        max_calls=5,
        max_estimated_input_tokens=5,
        max_output_tokens=500,
    )
    runtime.start_run()

    with pytest.raises(LiveModelBudgetExceeded, match="input-token limit"):
        runtime.before_call("openai", "extraction", "x" * 100, 100)


def test_fallback_uses_second_provider_after_schema_failure() -> None:
    extractor = FallbackOpportunityExtractor(
        [
            ProviderCandidate("openai", _FailingExtractor()),
            ProviderCandidate("anthropic", _WorkingExtractor()),
        ]
    )
    result = extractor.extract(
        OpportunityInput(raw_text="Product Manager consulting role", company_hint="Dream Cricket"),
        [],
    )

    assert result.company_name == "Dream Cricket"
    assert result.opportunity_type == OpportunityType.CONSULTING


def test_live_mode_accepts_one_complete_provider() -> None:
    settings = Settings(
        llm_mode="live",
        openai_api_key="test-key",
        openai_model="test-model",
        anthropic_api_key=None,
        anthropic_model=None,
    )

    assert settings.configured_live_providers == ("openai",)


def test_live_mode_rejects_incomplete_provider_configuration() -> None:
    with pytest.raises(ValueError, match="both OPENAI_API_KEY and OPENAI_MODEL"):
        Settings(llm_mode="live", openai_api_key="test-key", openai_model=None)


def test_live_mode_rejects_unconfigured_primary_provider() -> None:
    with pytest.raises(ValueError, match="Primary provider anthropic"):
        Settings(
            llm_mode="live",
            llm_primary_provider="anthropic",
            openai_api_key="test-key",
            openai_model="test-model",
        )
