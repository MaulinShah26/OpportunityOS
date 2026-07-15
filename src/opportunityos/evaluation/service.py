from __future__ import annotations

from collections import Counter, defaultdict

from opportunityos.application.scoring import (
    DEFAULT_HOLD_THRESHOLD,
    DEFAULT_MIN_EXTRACTION_CONFIDENCE,
    DEFAULT_PURSUE_THRESHOLD,
    apply_decision_gate_codes,
    decision_for_thresholds,
)
from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.enums import CriticSeverity, Decision
from opportunityos.domain.models import AnalysisRequest, AnalysisResult, utcnow
from opportunityos.evaluation.models import (
    DecisionPolicySnapshot,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationMetrics,
    EvaluationReport,
    ThresholdSimulation,
)

_DECISION_POSITION = {
    Decision.REJECT: 0,
    Decision.HOLD: 1,
    Decision.PURSUE: 2,
}
_DECISIONS = tuple(_DECISION_POSITION)


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _metadata_int(metadata: dict[str, str], key: str) -> int:
    try:
        return max(0, int(metadata.get(key, "0")))
    except (TypeError, ValueError):
        return 0


def _metadata_decision(metadata: dict[str, str], key: str) -> Decision | None:
    try:
        return Decision(metadata.get(key, ""))
    except ValueError:
        return None


def _metadata_gate_codes(metadata: dict[str, str]) -> list[str]:
    return [item.strip() for item in metadata.get("decision_gates", "").split(",") if item.strip()]


def _extraction_checks(case: EvaluationCase, result: AnalysisResult) -> tuple[int, int]:
    opportunity = result.opportunity
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


def _safe_rate(numerator: int | float, denominator: int) -> float:
    return float(numerator) / denominator if denominator else 0.0


def _decision_metrics(
    completed: list[EvaluationCaseResult],
    predictions: list[Decision],
) -> tuple[float, float, float, float]:
    accuracy = _safe_rate(
        sum(predicted == item.expected_decision for item, predicted in zip(completed, predictions, strict=True)),
        len(completed),
    )
    mean_distance = _safe_rate(
        sum(
            abs(_DECISION_POSITION[predicted] - _DECISION_POSITION[item.expected_decision])
            for item, predicted in zip(completed, predictions, strict=True)
        ),
        len(completed),
    )
    non_pursue = [
        (item, predicted)
        for item, predicted in zip(completed, predictions, strict=True)
        if item.expected_decision != Decision.PURSUE
    ]
    false_pursue_rate = _safe_rate(
        sum(predicted == Decision.PURSUE for _, predicted in non_pursue),
        len(non_pursue),
    )
    expected_pursue = [
        (item, predicted)
        for item, predicted in zip(completed, predictions, strict=True)
        if item.expected_decision == Decision.PURSUE
    ]
    false_reject_rate = _safe_rate(
        sum(predicted == Decision.REJECT for _, predicted in expected_pursue),
        len(expected_pursue),
    )
    return accuracy, mean_distance, false_pursue_rate, false_reject_rate


def _threshold_simulation(completed: list[EvaluationCaseResult]) -> ThresholdSimulation | None:
    expected_labels = {item.expected_decision for item in completed}
    if len(completed) < 5 or len(expected_labels) < 2:
        return None

    current_predictions = [item.predicted_decision for item in completed]
    if any(item is None for item in current_predictions):
        return None
    typed_current = [item for item in current_predictions if item is not None]
    current_accuracy, _, _, _ = _decision_metrics(completed, typed_current)

    best: tuple[tuple[float, float, float, int, int], ThresholdSimulation] | None = None
    for hold_threshold in range(20, 71):
        for pursue_threshold in range(hold_threshold + 1, 91):
            predictions = [
                apply_decision_gate_codes(
                    decision_for_thresholds(
                        fit_total=item.fit_score or 0,
                        extraction_confidence=item.extraction_confidence or 0.0,
                        has_hard_constraint_breach=bool(item.actual_hard_constraint_breach),
                        hold_threshold=hold_threshold,
                        pursue_threshold=pursue_threshold,
                        min_extraction_confidence=DEFAULT_MIN_EXTRACTION_CONFIDENCE,
                    ),
                    item.decision_gates,
                )
                for item in completed
            ]
            accuracy, mean_distance, false_pursue_rate, false_reject_rate = _decision_metrics(
                completed,
                predictions,
            )
            changed_case_count = sum(
                predicted != current
                for predicted, current in zip(predictions, typed_current, strict=True)
            )
            distance_from_default = abs(hold_threshold - DEFAULT_HOLD_THRESHOLD) + abs(
                pursue_threshold - DEFAULT_PURSUE_THRESHOLD
            )
            simulation = ThresholdSimulation(
                hold_threshold=hold_threshold,
                pursue_threshold=pursue_threshold,
                decision_accuracy=accuracy,
                mean_decision_distance=mean_distance,
                false_pursue_rate=false_pursue_rate,
                false_reject_rate=false_reject_rate,
                changed_case_count=changed_case_count,
                sample_warning=(
                    "Exploratory only: fewer than 12 frozen cases can make threshold suggestions unstable."
                    if len(completed) < 12
                    else "Simulation only: review case-level effects before changing production policy."
                ),
            )
            key = (
                false_pursue_rate,
                -accuracy,
                mean_distance,
                distance_from_default,
                changed_case_count,
            )
            if best is None or key < best[0]:
                best = (key, simulation)

    if best is None or best[1].decision_accuracy <= current_accuracy:
        return None
    return best[1]


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
            fit_dimensions = {item.name: item.score for item in analysis.fit_score.dimensions}
            fit_contributions = {
                item.name: round(item.score * item.weight * 100, 2)
                for item in analysis.fit_score.dimensions
            }
            score_based_decision = _metadata_decision(
                analysis.model_metadata,
                "score_based_decision",
            )
            decision_gates = _metadata_gate_codes(analysis.model_metadata)
            case_results.append(
                EvaluationCaseResult(
                    case_id=case.case_id,
                    name=case.name,
                    expected_decision=case.expected_decision,
                    predicted_decision=predicted,
                    score_based_decision=score_based_decision,
                    decision_gates=decision_gates,
                    extracted_company_name=analysis.opportunity.company_name,
                    extracted_title=analysis.opportunity.title,
                    extracted_opportunity_type=analysis.opportunity.opportunity_type,
                    correct=predicted == case.expected_decision,
                    decision_distance=abs(
                        _DECISION_POSITION[predicted] - _DECISION_POSITION[case.expected_decision]
                    ),
                    fit_score=analysis.fit_score.total,
                    extraction_confidence=analysis.opportunity.extraction_confidence,
                    fit_dimensions=fit_dimensions,
                    fit_contributions=fit_contributions,
                    distance_to_hold_threshold=analysis.fit_score.total - DEFAULT_HOLD_THRESHOLD,
                    distance_to_pursue_threshold=analysis.fit_score.total - DEFAULT_PURSUE_THRESHOLD,
                    expected_hard_constraint_breach=case.expected_hard_constraint_breach,
                    actual_hard_constraint_breach=actual_hard_breach,
                    hard_constraint_correct=hard_correct,
                    extraction_checks=extraction_checks,
                    extraction_checks_passed=extraction_passed,
                    evidence_count=len(analysis.opportunity.evidence),
                    hypothesis_count=len(analysis.hypotheses),
                    critic_passed=analysis.critic.passed,
                    critic_issue_codes=[item.code for item in analysis.critic.issues],
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
    predictions = [item.predicted_decision for item in completed if item.predicted_decision is not None]
    decision_accuracy, mean_distance, false_pursue_rate, false_reject_rate = _decision_metrics(
        completed,
        predictions,
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

    prediction_counts = Counter(item.value for item in predictions)
    gate_counts = Counter(code for item in completed for code in item.decision_gates)
    confusion_matrix = {
        expected.value: {predicted.value: 0 for predicted in _DECISIONS}
        for expected in _DECISIONS
    }
    for item, predicted in zip(completed, predictions, strict=True):
        confusion_matrix[item.expected_decision.value][predicted.value] += 1

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
        underprediction_rate=_safe_rate(
            sum(
                _DECISION_POSITION[predicted] < _DECISION_POSITION[item.expected_decision]
                for item, predicted in zip(completed, predictions, strict=True)
            ),
            len(completed),
        ),
        overprediction_rate=_safe_rate(
            sum(
                _DECISION_POSITION[predicted] > _DECISION_POSITION[item.expected_decision]
                for item, predicted in zip(completed, predictions, strict=True)
            ),
            len(completed),
        ),
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
        prediction_labels={decision.value: prediction_counts[decision.value] for decision in _DECISIONS},
        confusion_matrix=confusion_matrix,
        average_fit_by_expected_decision={
            label: sum(scores) / len(scores) for label, scores in fit_by_label.items()
        },
        score_ranges_by_expected_decision={
            label: {"minimum": min(scores), "maximum": max(scores), "average": sum(scores) / len(scores)}
            for label, scores in fit_by_label.items()
        },
        gated_case_count=sum(bool(item.decision_gates) for item in completed),
        decision_gate_counts=dict(gate_counts),
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
        decision_policy=DecisionPolicySnapshot(
            hold_threshold=DEFAULT_HOLD_THRESHOLD,
            pursue_threshold=DEFAULT_PURSUE_THRESHOLD,
            min_extraction_confidence=DEFAULT_MIN_EXTRACTION_CONFIDENCE,
        ),
        threshold_simulation=_threshold_simulation(completed),
        started_at=started_at,
        completed_at=utcnow(),
        metrics=metrics,
        cases=case_results,
    )
