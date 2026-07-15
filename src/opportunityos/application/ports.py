from __future__ import annotations

from typing import Protocol

from opportunityos.domain.models import (
    BusinessHypothesis,
    EvidenceClaim,
    OpportunityInput,
    OpportunityProfile,
    OutreachDraft,
    PersonalProfile,
)


class OpportunityExtractor(Protocol):
    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile: ...


class BusinessAnalyst(Protocol):
    def analyse(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
    ) -> list[BusinessHypothesis]: ...


class OutreachWriter(Protocol):
    def draft(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
        hypotheses: list[BusinessHypothesis],
    ) -> OutreachDraft: ...


class ResearchProvider(Protocol):
    def collect(self, source: OpportunityInput) -> list[EvidenceClaim]: ...


class ModelRuntime(Protocol):
    def start_run(self) -> None: ...

    def metadata(self) -> dict[str, str]: ...
