from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from anthropic import Anthropic
from pydantic import TypeAdapter

from opportunityos.domain.models import (
    BusinessHypothesis,
    EvidenceClaim,
    OpportunityInput,
    OpportunityProfile,
    OutreachDraft,
    PersonalProfile,
)
from opportunityos.infrastructure.llm.runtime import LiveModelRuntime, bounded_json, parse_json_text

T = TypeVar("T")
_HYPOTHESES = TypeAdapter(list[BusinessHypothesis])


def _text_from_message(message: object) -> str:
    content = getattr(message, "content", [])
    return "".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", "") == "text"
    )


class _AnthropicJSONProvider:
    provider_name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        runtime: LiveModelRuntime,
        timeout_seconds: float,
        max_prompt_chars: int,
        client: Any | None = None,
    ) -> None:
        self.client = client or Anthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
        )
        self.model = model
        self.runtime = runtime
        self.max_prompt_chars = max_prompt_chars

    def _request(
        self,
        *,
        role: str,
        payload: dict[str, Any],
        max_output_tokens: int,
        validator: Callable[[Any], T],
    ) -> T:
        prompt = bounded_json(payload, max_chars=self.max_prompt_chars)
        estimated = self.runtime.before_call(
            self.provider_name,
            role,
            prompt,
            max_output_tokens,
        )
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = validator(parse_json_text(_text_from_message(message)))
            usage = getattr(message, "usage", None)
            self.runtime.record_success(
                provider=self.provider_name,
                role=role,
                estimated_input_tokens=estimated,
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            )
            return parsed
        except Exception as exc:
            self.runtime.record_failure(
                provider=self.provider_name,
                role=role,
                estimated_input_tokens=estimated,
                error=exc,
            )
            raise


def _source_payload(source: OpportunityInput, max_chars: int) -> dict[str, Any]:
    payload = source.model_dump(mode="json")
    if payload.get("raw_text"):
        payload["raw_text"] = str(payload["raw_text"])[:max_chars]
    return payload


class AnthropicOpportunityExtractor(_AnthropicJSONProvider):
    def __init__(self, *, max_output_tokens: int, max_source_chars: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_output_tokens = max_output_tokens
        self.max_source_chars = max_source_chars

    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile:
        payload = {
            "instruction": (
                "Extract only facts supported by the supplied opportunity text and evidence. Do not infer missing "
                "compensation, location, seniority, responsibilities, or company facts. Use evidence IDs exactly "
                "as supplied. Return only one JSON object matching the schema."
            ),
            "source": _source_payload(source, self.max_source_chars),
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "schema": OpportunityProfile.model_json_schema(),
        }

        def validate(value: Any) -> OpportunityProfile:
            profile = OpportunityProfile.model_validate(value)
            profile.evidence = list(evidence)
            return profile

        return self._request(
            role="extraction",
            payload=payload,
            max_output_tokens=self.max_output_tokens,
            validator=validate,
        )


class AnthropicBusinessAnalyst(_AnthropicJSONProvider):
    def __init__(self, *, max_output_tokens: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_output_tokens = max_output_tokens

    def analyse(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
    ) -> list[BusinessHypothesis]:
        payload = {
            "instruction": (
                "Return at most three business hypotheses. Observed facts and supported inferences must cite one "
                "or more evidence IDs from the opportunity. Speculation must be labelled speculative and kept at "
                "confidence 0.60 or lower. Never claim internal company knowledge. Return only JSON."
            ),
            "profile": profile.model_dump(mode="json"),
            "opportunity": opportunity.model_dump(mode="json"),
            "schema": {"type": "array", "items": BusinessHypothesis.model_json_schema()},
        }
        return self._request(
            role="analysis",
            payload=payload,
            max_output_tokens=self.max_output_tokens,
            validator=_HYPOTHESES.validate_python,
        )


class AnthropicOutreachWriter(_AnthropicJSONProvider):
    def __init__(self, *, max_output_tokens: int, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.max_output_tokens = max_output_tokens

    def draft(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
        hypotheses: list[BusinessHypothesis],
    ) -> OutreachDraft:
        payload = {
            "instruction": (
                "Draft concise, direct, operator-like outreach. Use only the supplied profile facts and grounded "
                "hypotheses. Put every externally verifiable claim in grounded_claims using the exact hypothesis "
                "wording. Avoid generic networking language and exaggerated certainty. Return only JSON."
            ),
            "profile": profile.model_dump(mode="json"),
            "opportunity": opportunity.model_dump(mode="json"),
            "hypotheses": [item.model_dump(mode="json") for item in hypotheses],
            "schema": OutreachDraft.model_json_schema(),
        }
        return self._request(
            role="outreach",
            payload=payload,
            max_output_tokens=self.max_output_tokens,
            validator=OutreachDraft.model_validate,
        )
