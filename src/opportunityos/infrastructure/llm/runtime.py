from __future__ import annotations

import json
import math
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from opportunityos.application.ports import BusinessAnalyst, OpportunityExtractor, OutreachWriter
from opportunityos.domain.models import (
    BusinessHypothesis,
    EvidenceClaim,
    OpportunityInput,
    OpportunityProfile,
    OutreachDraft,
    PersonalProfile,
)


class LiveModelError(RuntimeError):
    """Base error for live-model execution."""


class LiveModelBudgetExceeded(LiveModelError):
    """Raised before a call when the configured per-analysis budget would be exceeded."""


class LiveModelUnavailable(LiveModelError):
    """Raised when every configured provider fails for a role."""


@dataclass(frozen=True)
class ModelCallEvent:
    provider: str
    role: str
    status: str
    estimated_input_tokens: int
    input_tokens: int
    output_tokens: int
    error_type: str | None = None


class LiveModelRuntime:
    """Tracks one analysis run and enforces hard call/token ceilings before paid calls."""

    def __init__(
        self,
        *,
        max_calls: int,
        max_estimated_input_tokens: int,
        max_output_tokens: int,
    ) -> None:
        self.max_calls = max_calls
        self.max_estimated_input_tokens = max_estimated_input_tokens
        self.max_output_tokens = max_output_tokens
        self._events: ContextVar[tuple[ModelCallEvent, ...]] = ContextVar("model_events", default=())
        self._calls: ContextVar[int] = ContextVar("model_calls", default=0)
        self._estimated_input: ContextVar[int] = ContextVar("model_estimated_input", default=0)
        self._reserved_output: ContextVar[int] = ContextVar("model_reserved_output", default=0)

    def start_run(self) -> None:
        self._events.set(())
        self._calls.set(0)
        self._estimated_input.set(0)
        self._reserved_output.set(0)

    def before_call(self, provider: str, role: str, prompt: str, max_output_tokens: int) -> int:
        estimated_input = max(1, math.ceil(len(prompt) / 4))
        calls = self._calls.get() + 1
        estimated_total = self._estimated_input.get() + estimated_input
        output_total = self._reserved_output.get() + max_output_tokens

        if calls > self.max_calls:
            raise LiveModelBudgetExceeded(
                f"Model call limit exceeded before {provider}:{role} ({calls}>{self.max_calls})"
            )
        if estimated_total > self.max_estimated_input_tokens:
            raise LiveModelBudgetExceeded(
                "Estimated input-token limit exceeded before model execution "
                f"({estimated_total}>{self.max_estimated_input_tokens})"
            )
        if output_total > self.max_output_tokens:
            raise LiveModelBudgetExceeded(
                "Reserved output-token limit exceeded before model execution "
                f"({output_total}>{self.max_output_tokens})"
            )

        self._calls.set(calls)
        self._estimated_input.set(estimated_total)
        self._reserved_output.set(output_total)
        return estimated_input

    def record_success(
        self,
        *,
        provider: str,
        role: str,
        estimated_input_tokens: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self._append(
            ModelCallEvent(
                provider=provider,
                role=role,
                status="success",
                estimated_input_tokens=estimated_input_tokens,
                input_tokens=max(0, input_tokens),
                output_tokens=max(0, output_tokens),
            )
        )

    def record_failure(
        self,
        *,
        provider: str,
        role: str,
        estimated_input_tokens: int,
        error: Exception,
    ) -> None:
        self._append(
            ModelCallEvent(
                provider=provider,
                role=role,
                status="failure",
                estimated_input_tokens=estimated_input_tokens,
                input_tokens=0,
                output_tokens=0,
                error_type=type(error).__name__,
            )
        )

    def metadata(self) -> dict[str, str]:
        events = self._events.get()
        successful = [event for event in events if event.status == "success"]
        failures = [event for event in events if event.status == "failure"]
        provider_sequence = ",".join(event.provider for event in successful)
        role_sequence = ",".join(f"{event.role}:{event.provider}" for event in successful)
        return {
            "model_calls": str(self._calls.get()),
            "successful_model_calls": str(len(successful)),
            "failed_model_calls": str(len(failures)),
            "estimated_input_tokens": str(self._estimated_input.get()),
            "reported_input_tokens": str(sum(event.input_tokens for event in successful)),
            "reported_output_tokens": str(sum(event.output_tokens for event in successful)),
            "provider_sequence": provider_sequence,
            "role_provider_sequence": role_sequence,
            "fallback_used": str(bool(failures)).lower(),
            "max_calls": str(self.max_calls),
            "max_estimated_input_tokens": str(self.max_estimated_input_tokens),
            "max_output_tokens": str(self.max_output_tokens),
        }

    def _append(self, event: ModelCallEvent) -> None:
        self._events.set((*self._events.get(), event))


def bounded_json(payload: dict[str, Any], *, max_chars: int) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(rendered) > max_chars:
        raise LiveModelBudgetExceeded(
            f"Prompt exceeds the configured character limit ({len(rendered)}>{max_chars})"
        )
    return rendered


def parse_json_text(value: str) -> Any:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    first_object = cleaned.find("{")
    first_array = cleaned.find("[")
    starts = [position for position in (first_object, first_array) if position >= 0]
    if starts:
        cleaned = cleaned[min(starts) :]
    last_object = cleaned.rfind("}")
    last_array = cleaned.rfind("]")
    end = max(last_object, last_array)
    if end >= 0:
        cleaned = cleaned[: end + 1]
    return json.loads(cleaned)


T = TypeVar("T")


@dataclass(frozen=True)
class ProviderCandidate(Generic[T]):
    name: str
    provider: T


def _all_failed(role: str, errors: list[tuple[str, Exception]]) -> LiveModelUnavailable:
    summary = "; ".join(f"{name}:{type(error).__name__}" for name, error in errors)
    return LiveModelUnavailable(f"All configured providers failed for {role}: {summary}")


class FallbackOpportunityExtractor:
    def __init__(self, candidates: list[ProviderCandidate[OpportunityExtractor]]) -> None:
        self._candidates = candidates

    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile:
        errors: list[tuple[str, Exception]] = []
        for candidate in self._candidates:
            try:
                return candidate.provider.extract(source, evidence)
            except LiveModelBudgetExceeded:
                raise
            except Exception as exc:  # provider and schema failures are eligible for fallback
                errors.append((candidate.name, exc))
        raise _all_failed("extraction", errors)


class FallbackBusinessAnalyst:
    def __init__(self, candidates: list[ProviderCandidate[BusinessAnalyst]]) -> None:
        self._candidates = candidates

    def analyse(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
    ) -> list[BusinessHypothesis]:
        errors: list[tuple[str, Exception]] = []
        for candidate in self._candidates:
            try:
                return candidate.provider.analyse(profile, opportunity)
            except LiveModelBudgetExceeded:
                raise
            except Exception as exc:
                errors.append((candidate.name, exc))
        raise _all_failed("analysis", errors)


class FallbackOutreachWriter:
    def __init__(self, candidates: list[ProviderCandidate[OutreachWriter]]) -> None:
        self._candidates = candidates

    def draft(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
        hypotheses: list[BusinessHypothesis],
    ) -> OutreachDraft:
        errors: list[tuple[str, Exception]] = []
        for candidate in self._candidates:
            try:
                return candidate.provider.draft(profile, opportunity, hypotheses)
            except LiveModelBudgetExceeded:
                raise
            except Exception as exc:
                errors.append((candidate.name, exc))
        raise _all_failed("outreach", errors)
