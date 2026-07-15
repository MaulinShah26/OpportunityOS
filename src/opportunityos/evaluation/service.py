from __future__ import annotations

from collections import defaultdict

from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.enums import CriticSeverity, Decision
from opportunityos.domain.models import AnalysisRequest, utcnow
from opportunityos.evaluation.models import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationMetrics,
    EvaluationReport,
)

_DECISION_POSITION = {
    Decision.REJECT: 0,
    Decision.HOLD: 1,
    Decision.PURSUE: 2,
}


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _metadata_int(metadata: dict[str, str], key: str) -> int:
    try:
        return max(0, int(metadata.get(key, "0")))
    except (TypeError, ValueError):
        return 0


def _extraction_checks(case: EvaluationCase, result: object) -> tuple[int, int]:
    opportunity = getattr(result, "opportunity")
    total = 0
    passed = 0

    if case.expected_opportunity_type is not None:
        total += 1
        passed += opportunity.opportunity_type == case.expected_opportunity_type
    if case.expected_remote_allowed is not None:
        total += 1
        passed += opportunity.remote_allowed is case.expected_remote_allowed

    actual_skills = {_normalise(item) for item in opportunity.required_skills}
    for expected in case.expected_required_skills:
        total += 1
        passed += _normalise(expected) in actual_skills

    actual_problem_areas = {_normalise(item) for item in opportunity.problem_areas}
    for expected in case.expected_problem_areas:
        total += 1
        passed += _normalise(expected) in actual_problem_areas
    return total, passed


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def evaluate_dataset(
    dataset: EvaluationDataset,
    service: AnalyseOpportunityService,
    *,
    mode: str,
    provider_order: str,
    model_names: dict[str, str] | None = None,
) -> EvaluationReport:
    started_at = utcnow()
    case_results: list[EvaluationCaseResult] = []

    for case in dataset.cases:
        try:
            analysis = service.execute(
                AnalysisRequest(profile=dataset.profile, opportunity=case.opportunity)
            )
            predicted = analysis.recommendation.decision
            actual_hard_breach = bool(analysis.fit_score.hard_constraint_breaches)
            hard_correct = (
                actual_hard_breach == case.expected_hard_constraint_breach
                if case.expected_hard_constraint_breach is not None
                else None
            )
            extraction_checks, extraction_passed = _extraction_checks(case, analysis)
            case_results.append(
                EvaluationCaseResult(
                    case_id=case.case_id,
                    name=case.name,
                    expected_decision=case.expected_decision,
                    predicted_decision=predicted,
                    correct=predicted == case.expected_decision,
                    decision_distance=abs(
                        _DECISION_POSITION[predicted] - _DECISION_POSITION[case.expected_decision]
                    ),
                    fit_score=analysis.fit_score.total,
                    expected_hard_constraint_breach=case.expected_hard_constraint_breach,
                    actual_hard_constraint_breach=actual_hard_breach,
                    hard_constraint_correct=hard_correct,
                    extraction_checks=extraction_checks,
                    extraction_checks_passed=extraction_passed,
                    evidence_count=len(analysis.opportunity.evidence),
                    hypothesis_count=len(analysis.hypotheses),
                    critic_passed=analysis.critic.passed,
                    blocking_issue_count=sum(
                        issue.severity == CriticSeverity.BLOCKING for issue in analysis.critic.issues
                    ),
                    warning_issue_count=sum(
                        issue.severity == CriticSeverity.WARNING for issue in analysis.critic.issues
                    ),
                    analysis=analysis,
                )
            )
        except Exception as exc:
            case_results.append(
                EvaluationCaseResult(
                    case_id=case.case_id,
                    name=case.name,
                    expected_decision=case.expected_decision,
                    error_type=type(exc).__name__,
                    error_message=str(exc)[:1000],
                )
            )

    completed = [item for item in case_results if item.analysis is not None]
    failed_count = len(case_results) - len(completed)
    decision_accuracy = _safe_rate(sum(item.correct for item in completed), len(completed))
    mean_distance = _safe_rate(
        sum(item.decision_distance or 0 for item in completed),
        len(completed),
    )

    non_pursue = [item for item in completed if item.expected_decision != Decision.PURSUE]
    false_pursue_rate = _safe_rate(
        sum(item.predicted_decision == Decision.PURSUE for item in non_pursue),
        len(non_pursue),
    )
    expected_pursue = [item for item in completed if item.expected_decision == Decision.PURSUE]
    false_reject_rate = _safe_rate(
        sum(item.predicted_decision == Decision.REJECT for item in expected_pursue),
        len(expected_pursue),
    )

    extraction_total = sum(item.extraction_checks for item in completed)
    extraction_passed = sum(item.extraction_checks_passed for item in completed)
    labelled_hard_constraints = [
        item for item in completed if item.hard_constraint_correct is not None
    ]

    fit_by_label: dict[str, list[int]] = defaultdict(list)
    for item in completed:
        if item.fit_score is not None:
            fit_by_label[item.expected_decision.value].append(item.fit_score)

    total_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0
    fallback_case_count = 0
    for item in completed:
        metadata = item.analysis.model_metadata if item.analysis is not None else {}
        total_calls += _metadata_int(metadata, "model_calls")
        total_input_tokens += _metadata_int(metadata, "reported_input_tokens")
        total_output_tokens += _metadata_int(metadata, "reported_output_tokens")
        fallback_case_count += metadata.get("fallback_used", "false").casefold() == "true"

    metrics = EvaluationMetrics(
        case_count=len(case_results),
        completed_count=len(completed),
        failed_count=failed_count,
        decision_accuracy=decision_accuracy,
        mean_decision_distance=mean_distance,
        false_pursue_rate=false_pursue_rate,
        false_reject_rate=false_reject_rate,
        evidence_present_rate=_safe_rate(
            sum(item.evidence_count > 0 for item in completed),
            len(completed),
        ),
        critic_pass_rate=_safe_rate(
            sum(bool(item.critic_passed) for item in completed),
            len(completed),
        ),
        extraction_accuracy=(
            _safe_rate(extraction_passed, extraction_total) if extraction_total else None
        ),
        hard_constraint_accuracy=(
            _safe_rate(
                sum(bool(item.hard_constraint_correct) for item in labelled_hard_constraints),
                len(labelled_hard_constraints),
            )
            if labelled_hard_constraints
            else None
        ),
        average_fit_by_expected_decision={
            label: sum(scores) / len(scores) for label, scores in fit_by_label.items()
        },
        total_model_calls=total_calls,
        total_reported_input_tokens=total_input_tokens,
        total_reported_output_tokens=total_output_tokens,
        fallback_case_count=fallback_case_count,
    )
    return EvaluationReport(
        dataset_id=dataset.dataset_id,
        dataset_name=dataset.name,
        user_id=dataset.profile.user_id,
        mode=mode,
        provider_order=provider_order,
        model_names=model_names or {},
        started_at=started_at,
        completed_at=utcnow(),
        metrics=metrics,
        cases=case_results,
    )
