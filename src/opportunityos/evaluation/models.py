from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from opportunityos.domain.enums import Decision, FeedbackAction, FeedbackReason, OpportunityType
from opportunityos.domain.models import AnalysisResult, OpportunityInput, PersonalProfile, utcnow


class ExtractionExpectation(BaseModel):
    company_name: str | None = Field(default=None, max_length=240)
    title: str | None = Field(default=None, max_length=300)
    opportunity_type: OpportunityType | None = None
    location: str | None = Field(default=None, max_length=300)
    remote_allowed: bool | None = None
    required_skills: list[str] = Field(default_factory=list)
    problem_areas: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)


class EvaluationCandidate(BaseModel):
    case_id: str
    name: str
    opportunity: OpportunityInput
    expected_decision: Decision
    source_analysis_id: UUID
    label_action: FeedbackAction | None = None
    label_reasons: list[FeedbackReason] = Field(default_factory=list)
    current_extraction: ExtractionExpectation
    previously_frozen: bool = False
    previous_dataset_names: list[str] = Field(default_factory=list)


class EvaluationCandidateCollection(BaseModel):
    user_id: UUID
    candidates: list[EvaluationCandidate]


class EvaluationCaseLabel(BaseModel):
    source_analysis_id: UUID
    expected: ExtractionExpectation


class EvaluationCaseCorrection(BaseModel):
    case_id: str = Field(min_length=2, max_length=120)
    expected_decision: Decision
    expected: ExtractionExpectation


class EvaluationCase(BaseModel):
    case_id: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=240)
    opportunity: OpportunityInput
    expected_decision: Decision
    expected_company_name: str | None = Field(default=None, max_length=240)
    expected_title: str | None = Field(default=None, max_length=300)
    expected_opportunity_type: OpportunityType | None = None
    expected_location: str | None = Field(default=None, max_length=300)
    expected_remote_allowed: bool | None = None
    expected_required_skills: list[str] = Field(default_factory=list)
    expected_problem_areas: list[str] = Field(default_factory=list)
    expected_responsibilities: list[str] = Field(default_factory=list)
    expected_hard_constraint_breach: bool | None = None
    source_analysis_id: UUID | None = None
    label_action: FeedbackAction | None = None
    label_reasons: list[FeedbackReason] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=1000)


class EvaluationDataset(BaseModel):
    dataset_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=2, max_length=200)
    schema_version: str = "1.4"
    revision: int = Field(default=1, ge=1)
    parent_dataset_ids: list[UUID] = Field(default_factory=list)
    revision_reason: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=utcnow)
    profile: PersonalProfile
    cases: list[EvaluationCase] = Field(min_length=1)
    source: str = "explicit_user_feedback"
    frozen: bool = True


class EvaluationDatasetSummary(BaseModel):
    dataset_id: UUID
    user_id: UUID
    name: str
    revision: int = Field(default=1, ge=1)
    parent_dataset_ids: list[UUID] = Field(default_factory=list)
    revision_reason: str | None = Field(default=None, max_length=1000)
    case_count: int = Field(ge=0)
    decision_labels: dict[str, int] = Field(default_factory=dict)
    extraction_label_count: int = Field(default=0, ge=0)
    ready_for_comparison: bool
    created_at: datetime


class EvaluationDatasetCollection(BaseModel):
    user_id: UUID
    datasets: list[EvaluationDatasetSummary]


class CreateEvaluationDatasetRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    extraction_labels: list[EvaluationCaseLabel] = Field(default_factory=list)


class ExtendEvaluationDatasetRequest(BaseModel):
    extraction_labels: list[EvaluationCaseLabel] = Field(min_length=1)


class MergeEvaluationDatasetsRequest(BaseModel):
    source_dataset_ids: list[UUID] = Field(min_length=2)


class CorrectEvaluationDatasetRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    corrections: list[EvaluationCaseCorrection] = Field(min_length=1)


class DecisionPolicySnapshot(BaseModel):
    hold_threshold: int = Field(default=45, ge=0, le=100)
    pursue_threshold: int = Field(default=72, ge=0, le=100)
    min_extraction_confidence: float = Field(default=0.60, ge=0.0, le=1.0)


class ThresholdSimulation(BaseModel):
    hold_threshold: int = Field(ge=0, le=100)
    pursue_threshold: int = Field(ge=0, le=100)
    decision_accuracy: float = Field(ge=0.0, le=1.0)
    mean_decision_distance: float = Field(ge=0.0, le=2.0)
    false_pursue_rate: float = Field(ge=0.0, le=1.0)
    false_reject_rate: float = Field(ge=0.0, le=1.0)
    changed_case_count: int = Field(ge=0)
    sample_warning: str


class EvaluationCaseResult(BaseModel):
    case_id: str
    name: str
    expected_decision: Decision
    predicted_decision: Decision | None = None
    score_based_decision: Decision | None = None
    decision_gates: list[str] = Field(default_factory=list)
    extracted_company_name: str | None = None
    extracted_title: str | None = None
    extracted_opportunity_type: OpportunityType | None = None
    correct: bool = False
    decision_distance: int | None = None
    fit_score: int | None = None
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    extraction_field_results: dict[str, bool] = Field(default_factory=dict)
    extraction_case_correct: bool | None = None
    fit_dimensions: dict[str, float] = Field(default_factory=dict)
    fit_contributions: dict[str, float] = Field(default_factory=dict)
    distance_to_hold_threshold: int | None = None
    distance_to_pursue_threshold: int | None = None
    expected_hard_constraint_breach: bool | None = None
    actual_hard_constraint_breach: bool | None = None
    hard_constraint_correct: bool | None = None
    extraction_checks: int = 0
    extraction_checks_passed: int = 0
    evidence_count: int = 0
    hypothesis_count: int = 0
    critic_passed: bool | None = None
    critic_issue_codes: list[str] = Field(default_factory=list)
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
    underprediction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    overprediction_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_present_rate: float = Field(ge=0.0, le=1.0)
    critic_pass_rate: float = Field(ge=0.0, le=1.0)
    extraction_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    extraction_case_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    extraction_accuracy_by_field: dict[str, float] = Field(default_factory=dict)
    extraction_labelled_case_count: int = Field(default=0, ge=0)
    hard_constraint_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    prediction_labels: dict[str, int] = Field(default_factory=dict)
    confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    average_fit_by_expected_decision: dict[str, float] = Field(default_factory=dict)
    score_ranges_by_expected_decision: dict[str, dict[str, float]] = Field(default_factory=dict)
    gated_case_count: int = Field(default=0, ge=0)
    decision_gate_counts: dict[str, int] = Field(default_factory=dict)
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
    decision_policy: DecisionPolicySnapshot = Field(default_factory=DecisionPolicySnapshot)
    threshold_simulation: ThresholdSimulation | None = None
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
