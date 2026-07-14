from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl, model_validator

from opportunityos.domain.enums import (
    ConstraintKind,
    CriticSeverity,
    Decision,
    EvidenceType,
    FeedbackAction,
    FeedbackReason,
    MemoryAction,
    MemoryCategory,
    MemorySource,
    MemoryStatus,
    OpportunityType,
)

Score = Annotated[float, Field(ge=0.0, le=1.0)]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Capability(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    proficiency: Score = 0.7
    evidence: list[str] = Field(default_factory=list)


class WeightedPreference(BaseModel):
    key: str = Field(min_length=2, max_length=120)
    weight: Score
    explicit: bool = True
    confidence: Score = 1.0
    last_updated_at: datetime = Field(default_factory=utcnow)


class Constraint(BaseModel):
    key: str = Field(min_length=2, max_length=120)
    kind: ConstraintKind
    accepted_values: list[str] = Field(default_factory=list)
    rejected_values: list[str] = Field(default_factory=list)
    penalty: Score = 1.0


class Aspiration(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    weight: Score = 0.7


class PersonalProfile(BaseModel):
    user_id: UUID = Field(default_factory=uuid4)
    display_name: str = Field(min_length=2, max_length=160)
    headline: str = Field(min_length=2, max_length=300)
    capabilities: list[Capability] = Field(min_length=1)
    preferences: list[WeightedPreference] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    aspirations: list[Aspiration] = Field(default_factory=list)
    target_problem_areas: list[str] = Field(default_factory=list)


class OpportunityInput(BaseModel):
    source_url: HttpUrl | None = None
    raw_text: str | None = Field(default=None, max_length=100_000)
    company_hint: str | None = Field(default=None, max_length=250)

    @model_validator(mode="after")
    def require_source(self) -> OpportunityInput:
        if not self.source_url and not (self.raw_text and self.raw_text.strip()):
            raise ValueError("Provide source_url or raw_text")
        return self


class EvidenceClaim(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    claim: str = Field(min_length=3)
    claim_type: EvidenceType
    source_url: HttpUrl | None = None
    supporting_excerpt: str = Field(min_length=1, max_length=5000)
    confidence: Score
    retrieved_at: datetime = Field(default_factory=utcnow)


class OpportunityProfile(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    company_name: str = Field(min_length=2, max_length=250)
    title: str = Field(min_length=2, max_length=300)
    opportunity_type: OpportunityType = OpportunityType.UNKNOWN
    location: str | None = None
    remote_allowed: bool | None = None
    seniority: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    problem_areas: list[str] = Field(default_factory=list)
    compensation_text: str | None = None
    evidence: list[EvidenceClaim] = Field(default_factory=list)
    extraction_confidence: Score = 0.5


class BusinessHypothesis(BaseModel):
    statement: str = Field(min_length=3)
    claim_type: EvidenceType
    rationale: str = Field(min_length=3)
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence: Score


class ScoreDimension(BaseModel):
    name: str
    score: Score
    weight: Score
    explanation: str


class FitScore(BaseModel):
    total: int = Field(ge=0, le=100)
    dimensions: list[ScoreDimension]
    hard_constraint_breaches: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    decision: Decision
    rationale: str
    risks: list[str] = Field(default_factory=list)
    next_action: str


class OutreachDraft(BaseModel):
    subject: str | None = None
    body: str
    grounded_claims: list[str] = Field(default_factory=list)
    claims_to_avoid: list[str] = Field(default_factory=list)


class GuardrailIssue(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    message: str = Field(min_length=3, max_length=1000)
    severity: CriticSeverity
    claim: str | None = Field(default=None, max_length=2000)


class CriticResult(BaseModel):
    passed: bool
    block_outreach: bool = False
    issues: list[GuardrailIssue] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    blocked_draft: OutreachDraft | None = None
    reviewed_at: datetime = Field(default_factory=utcnow)


def legacy_unreviewed_critic() -> CriticResult:
    return CriticResult(
        passed=False,
        issues=[
            GuardrailIssue(
                code="legacy_unreviewed",
                message="This stored analysis predates recommendation guardrails.",
                severity=CriticSeverity.WARNING,
            )
        ],
    )


class AnalysisResult(BaseModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    opportunity: OpportunityProfile
    hypotheses: list[BusinessHypothesis]
    fit_score: FitScore
    recommendation: Recommendation
    outreach: OutreachDraft | None = None
    critic: CriticResult = Field(default_factory=legacy_unreviewed_critic)
    generated_at: datetime = Field(default_factory=utcnow)
    orchestrator: str = "local"
    model_metadata: dict[str, str] = Field(default_factory=dict)


class AnalysisRequest(BaseModel):
    profile: PersonalProfile
    opportunity: OpportunityInput


class FeedbackEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    analysis_id: UUID
    action: FeedbackAction
    reasons: list[FeedbackReason] = Field(default_factory=list)
    explicit: bool = True
    created_at: datetime = Field(default_factory=utcnow)


class FeedbackRequest(BaseModel):
    profile: PersonalProfile
    feedback: FeedbackEvent
    opportunity_type: OpportunityType | None = None
    company_industry: str | None = None


class FeedbackResponse(BaseModel):
    updated_profile: PersonalProfile
    applied_updates: list[str]


class ResumeOnboardingRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=160)
    headline: str | None = Field(default=None, max_length=300)
    email: str | None = Field(default=None, max_length=320)
    resume_text: str = Field(min_length=40, max_length=200_000)
    preferences: list[WeightedPreference] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    aspirations: list[Aspiration] = Field(default_factory=list)
    target_problem_areas: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    profile: PersonalProfile
    email: str | None = None
    inferred_capabilities: list[str] = Field(default_factory=list)
    inferred_problem_areas: list[str] = Field(default_factory=list)


class PersistedAnalysisRequest(BaseModel):
    opportunity: OpportunityInput


class PersistedFeedbackRequest(BaseModel):
    feedback: FeedbackEvent
    company_industry: str | None = None


class UserActivitySummary(BaseModel):
    user_id: UUID
    analysis_count: int = Field(ge=0)


class MemoryItem(BaseModel):
    id: UUID
    user_id: UUID
    category: MemoryCategory
    key: str
    value: dict[str, object]
    source: MemorySource
    confidence: Score
    status: MemoryStatus
    active: bool
    is_user_overridden: bool
    created_at: datetime
    updated_at: datetime


class MemoryCollection(BaseModel):
    user_id: UUID
    items: list[MemoryItem]


class MemoryMutationRequest(BaseModel):
    action: MemoryAction
    key: str | None = Field(default=None, min_length=2, max_length=180)
    value: dict[str, object] | None = None
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_update_payload(self) -> MemoryMutationRequest:
        if self.action == MemoryAction.UPDATE and self.value is None:
            raise ValueError("Update action requires value")
        return self


class MemoryAuditEvent(BaseModel):
    id: UUID
    user_id: UUID
    memory_item_id: UUID | None = None
    action: str
    actor: str
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    reason: str | None = None
    created_at: datetime


class MemoryAuditCollection(BaseModel):
    user_id: UUID
    events: list[MemoryAuditEvent]
