from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from opportunityos.domain.enums import Decision, FeedbackAction, FeedbackReason, OpportunityType
from opportunityos.domain.models import AnalysisResult, OpportunityInput, PersonalProfile, utcnow


class EvaluationCase(BaseModel):
    case_id: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=240)
    opportunity: OpportunityInput
    expected_decision: Decision
    expected_opportunity_type: OpportunityType | None = None
    expected_remote_allowed: bool | None = None
    expected_required_skills: list[str] = Field(default_factory=list)
    expected_problem_areas: list[str] = Field(default_factory=list)
    expected_hard_constraint_breach: bool | None = None
    source_analysis_id: UUID | None = None
    label_action: FeedbackAction | None = None
    label_reasons: list[FeedbackReason] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=1000)


class EvaluationDataset(BaseModel):
    dataset_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=2, max_length=200)
    schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=utcnow)
    profile: PersonalProfile
    cases: list[EvaluationCase] = Field(min_length=1)
    source: str = "explicit_user_feedback"
    frozen: bool = True


class EvaluationDatasetSummary(BaseModel):
    dataset_id: UUID
    user_id: UUID
    name: str
    case_count: int = Field(ge=0)
    decision_labels: dict[str, int] = Field(default_factory=dict)
    ready_for_comparison: bool
    created_at: datetime


class EvaluationDatasetCollection(BaseModel):
    user_id: UUID
    datasets: list[EvaluationDatasetSummary]


class CreateEvaluationDatasetRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class EvaluationCaseResult(BaseModel):
    case_id: str
    name: str
    expected_decision: Decision
    predicted_decision: Decision | None = None
    correct: bool = False
    decision_distance: int | None = None
    fit_score: int | None = None
    expected_hard_constraint_breach: bool | None = None
    actual_hard_constraint_breach: bool | None = None
    hard_constraint_correct: bool | None = None
    extraction_checks: int = 0
    extraction_checks_passed: int = 0
    evidence_count: int = 0
    hypothesis_count: int = 0
    critic_passed: bool | None = None
    blocking_issue_count: int = 0
    warning_issue_count: int = 0
    analysis: AnalysisResult | None = None
    error_type: str | None = None
    error_message: str | None = None


class EvaluationMetrics(BaseModel):
    case_count: int = Field(ge=0)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    decision_accuracy: float = Field(ge=0.0, le=1.0)
    mean_decision_distance: float = Field(ge=0.0, le=2.0)
    false_pursue_rate: float = Field(ge=0.0, le=1.0)
    false_reject_rate: float = Field(ge=0.0, le=1.0)
    evidence_present_rate: float = Field(ge=0.0, le=1.0)
    critic_pass_rate: float = Field(ge=0.0, le=1.0)
    extraction_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    hard_constraint_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    average_fit_by_expected_decision: dict[str, float] = Field(default_factory=dict)
    total_model_calls: int = Field(ge=0)
    total_reported_input_tokens: int = Field(ge=0)
    total_reported_output_tokens: int = Field(ge=0)
    fallback_case_count: int = Field(ge=0)


class EvaluationReport(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    dataset_id: UUID
    dataset_name: str
    user_id: UUID
    mode: str
    provider_order: str
    model_names: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime = Field(default_factory=utcnow)
    metrics: EvaluationMetrics
    cases: list[EvaluationCaseResult]


class EvaluationRunSummary(BaseModel):
    run_id: UUID
    dataset_id: UUID
    mode: str
    provider_order: str
    decision_accuracy: float
    false_pursue_rate: float
    case_count: int
    created_at: datetime


class EvaluationRunCollection(BaseModel):
    dataset_id: UUID
    runs: list[EvaluationRunSummary]
