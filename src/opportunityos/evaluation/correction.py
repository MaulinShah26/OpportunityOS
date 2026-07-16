from __future__ import annotations

from uuid import UUID

from opportunityos.evaluation.models import (
    CorrectEvaluationDatasetRequest,
    EvaluationCase,
    EvaluationDataset,
)


class EvaluationCorrectionError(ValueError):
    """Raised when a requested label correction cannot produce a valid revision."""


def _label_contract(case: EvaluationCase) -> dict:
    return {
        "expected_decision": case.expected_decision.value,
        "expected_company_name": case.expected_company_name,
        "expected_title": case.expected_title,
        "expected_opportunity_type": (
            case.expected_opportunity_type.value if case.expected_opportunity_type else None
        ),
        "expected_location": case.expected_location,
        "expected_remote_allowed": case.expected_remote_allowed,
        "expected_required_skills": case.expected_required_skills,
        "expected_problem_areas": case.expected_problem_areas,
        "expected_responsibilities": case.expected_responsibilities,
    }


def _corrected_case_name(case: EvaluationCase, company_name: str | None, title: str | None) -> str:
    company = company_name or case.expected_company_name or case.opportunity.company_hint
    role = title or case.expected_title or case.opportunity.role_hint
    if company and role:
        return f"{company} — {role}"[:240]
    if company:
        return f"{company} — opportunity"[:240]
    if role:
        return role[:240]
    return case.name


def correct_evaluation_dataset(
    store: object,
    user_id: UUID,
    dataset_id: UUID,
    request: CorrectEvaluationDatasetRequest,
) -> EvaluationDataset:
    """Create a new immutable revision with corrected human labels.

    The original profile snapshot, opportunity inputs, source analysis identifiers,
    and prior dataset remain unchanged. Every case must be reviewed so a correction
    revision cannot silently omit part of the benchmark.
    """

    base = store.get_evaluation_dataset(user_id, dataset_id)
    correction_map = {item.case_id: item for item in request.corrections}
    if len(correction_map) != len(request.corrections):
        raise EvaluationCorrectionError("Each benchmark case may appear only once in a correction revision.")

    expected_case_ids = {case.case_id for case in base.cases}
    supplied_case_ids = set(correction_map)
    missing = sorted(expected_case_ids - supplied_case_ids)
    unknown = sorted(supplied_case_ids - expected_case_ids)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing {len(missing)} case(s)")
        if unknown:
            details.append(f"containing {len(unknown)} unknown case(s)")
        raise EvaluationCorrectionError(
            "Review and submit every case in the frozen dataset before creating a corrected revision: "
            + ", ".join(details)
            + "."
        )

    corrected_cases: list[EvaluationCase] = []
    changed_case_count = 0
    correction_note = f"Label correction: {request.reason}"[:1000]
    for case in base.cases:
        correction = correction_map[case.case_id]
        expected = correction.expected
        notes = correction_note
        if case.notes:
            notes = f"{case.notes} | {correction_note}"[:1000]
        corrected = case.model_copy(
            update={
                "name": _corrected_case_name(case, expected.company_name, expected.title),
                "expected_decision": correction.expected_decision,
                "expected_company_name": expected.company_name,
                "expected_title": expected.title,
                "expected_opportunity_type": expected.opportunity_type,
                "expected_location": expected.location,
                "expected_remote_allowed": expected.remote_allowed,
                "expected_required_skills": expected.required_skills,
                "expected_problem_areas": expected.problem_areas,
                "expected_responsibilities": expected.responsibilities,
                "notes": notes,
            }
        )
        if _label_contract(corrected) != _label_contract(case):
            changed_case_count += 1
        corrected_cases.append(corrected)

    if changed_case_count == 0:
        raise EvaluationCorrectionError(
            "No benchmark labels changed. Update at least one decision or extraction field before creating a correction revision."
        )

    corrected_dataset = EvaluationDataset(
        name=base.name,
        schema_version="1.4",
        revision=store._next_revision(user_id, base.name),
        parent_dataset_ids=[dataset_id],
        revision_reason=request.reason,
        profile=base.profile,
        cases=corrected_cases,
        source="corrected_frozen_dataset_labels",
    )
    return store._persist_dataset(user_id, corrected_dataset)
