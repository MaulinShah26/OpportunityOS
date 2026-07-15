from __future__ import annotations

import json
from types import SimpleNamespace

from opportunityos.domain.enums import EvidenceType, OpportunityType
from opportunityos.domain.models import (
    Capability,
    EvidenceClaim,
    OpportunityInput,
    OpportunityProfile,
    PersonalProfile,
)
from opportunityos.infrastructure.llm.anthropic_provider import AnthropicBusinessAnalyst
from opportunityos.infrastructure.llm.openai_provider import OpenAIOpportunityExtractor
from opportunityos.infrastructure.llm.runtime import LiveModelRuntime


class _FakeOpenAIResponses:
    def create(self, **_: object) -> object:
        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "company_name": "Dream Cricket",
                    "title": "Senior Product Manager",
                    "opportunity_type": "consulting",
                    "required_skills": ["product management"],
                    "responsibilities": [],
                    "problem_areas": ["analytics"],
                    "evidence": [],
                    "extraction_confidence": 0.85,
                }
            ),
            usage=SimpleNamespace(input_tokens=120, output_tokens=80),
        )


class _FakeOpenAIClient:
    responses = _FakeOpenAIResponses()


class _FakeAnthropicMessages:
    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id

    def create(self, **_: object) -> object:
        payload = [
            {
                "statement": "The role explicitly requires product management and analytics.",
                "claim_type": "supported_inference",
                "rationale": "Those requirements are present in the supplied role text.",
                "evidence_ids": [self.evidence_id],
                "confidence": 0.75,
            }
        ]
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(payload))],
            usage=SimpleNamespace(input_tokens=150, output_tokens=90),
        )


class _FakeAnthropicClient:
    def __init__(self, evidence_id: str) -> None:
        self.messages = _FakeAnthropicMessages(evidence_id)


def _runtime() -> LiveModelRuntime:
    runtime = LiveModelRuntime(
        max_calls=5,
        max_estimated_input_tokens=20_000,
        max_output_tokens=6_000,
    )
    runtime.start_run()
    return runtime


def test_openai_extractor_validates_json_and_records_usage() -> None:
    runtime = _runtime()
    evidence = EvidenceClaim(
        claim="Dream Cricket is hiring a Senior Product Manager.",
        claim_type=EvidenceType.OBSERVED_FACT,
        supporting_excerpt="Senior Product Manager consulting role with product management and analytics.",
        confidence=0.95,
    )
    provider = OpenAIOpportunityExtractor(
        api_key="test",
        model="test-model",
        runtime=runtime,
        timeout_seconds=5,
        max_prompt_chars=20_000,
        max_output_tokens=1_200,
        max_source_chars=10_000,
        client=_FakeOpenAIClient(),
    )

    result = provider.extract(
        OpportunityInput(raw_text=evidence.supporting_excerpt, company_hint="Dream Cricket"),
        [evidence],
    )

    assert result.opportunity_type == OpportunityType.CONSULTING
    assert result.evidence == [evidence]
    assert runtime.metadata()["reported_output_tokens"] == "80"


def test_anthropic_analyst_validates_json_and_records_usage() -> None:
    runtime = _runtime()
    evidence = EvidenceClaim(
        claim="The role requires product management and analytics.",
        claim_type=EvidenceType.OBSERVED_FACT,
        supporting_excerpt="Product management and analytics are required.",
        confidence=0.95,
    )
    provider = AnthropicBusinessAnalyst(
        api_key="test",
        model="test-model",
        runtime=runtime,
        timeout_seconds=5,
        max_prompt_chars=20_000,
        max_output_tokens=1_600,
        client=_FakeAnthropicClient(str(evidence.id)),
    )
    profile = PersonalProfile(
        display_name="Test User",
        headline="Product analytics leader",
        capabilities=[Capability(name="product management", proficiency=0.8)],
    )
    opportunity = OpportunityProfile(
        company_name="Dream Cricket",
        title="Senior Product Manager",
        opportunity_type=OpportunityType.CONSULTING,
        evidence=[evidence],
        extraction_confidence=0.9,
    )

    result = provider.analyse(profile, opportunity)

    assert len(result) == 1
    assert result[0].evidence_ids == [evidence.id]
    assert runtime.metadata()["reported_input_tokens"] == "150"
