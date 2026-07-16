from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID

from sqlalchemy import select

from opportunityos.domain.enums import Decision, FeedbackAction, FeedbackReason
from opportunityos.domain.models import AnalysisResult, OpportunityInput, PersonalProfile
from opportunityos.evaluation.models import (
    EvaluationCandidate,
    EvaluationCase,
    EvaluationCaseLabel,
    EvaluationDataset,
    EvaluationDatasetSummary,
    EvaluationReport,
    EvaluationRunSummary,
    ExtractionExpectation,
)
from opportunityos.infrastructure.database.models import (
    AnalysisRunRecord,
    BehaviourEventRecord,
    EvaluationDatasetRecord,
    EvaluationRunRecord,
    OpportunityRecord,
    PersonalProfileRecord,
)


class EvaluationDatasetNotFoundError(LookupError):
    pass


class EvaluationRunNotFoundError(LookupError):
    pass


class EvaluationDatasetEmptyError(ValueError):
    pass


_FEEDBACK_TO_DECISION = {
    FeedbackAction.PURSUE: Decision.PURSUE,
    FeedbackAction.RELEVANT: Decision.PURSUE,
    FeedbackAction.SAVE: Decision.HOLD,
    FeedbackAction.MAYBE_LATER: Decision.HOLD,
    FeedbackAction.REJECT: Decision.REJECT,
    FeedbackAction.NOT_RELEVANT: Decision.REJECT,
}


def _feedback_action(value: str) -> FeedbackAction | None:
    return FeedbackAction(value) if value in FeedbackAction._value2member_map_ else None


def _feedback_reasons(payload: dict) -> list[FeedbackReason]:
    return [
        FeedbackReason(item)
        for item in payload.get("reasons", [])
        if item in FeedbackReason._value2member_map_
    ]


def _normalise_dataset_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _has_extraction_labels(case: EvaluationCase) -> bool:
    return any(
        [
            case.expected_company_name,
            case.expected_title,
            case.expected_opportunity_type is not None,
            case.expected_location,
            case.expected_remote_allowed is not None,
            case.expected_required_skills,
            case.expected_problem_areas,
            case.expected_responsibilities,
        ]
    )


def _dataset_summary(record: EvaluationDatasetRecord, revision: int) -> EvaluationDatasetSummary:
    labels = {str(key): int(value) for key, value in record.decision_labels_json.items()}
    non_pursue = labels.get(Decision.HOLD.value, 0) + labels.get(Decision.REJECT.value, 0)
    ready = record.case_count >= 5 and labels.get(Decision.PURSUE.value, 0) > 0 and non_pursue > 0
    dataset = EvaluationDataset.model_validate(record.dataset_json)
    return EvaluationDatasetSummary(
        dataset_id=UUID(record.id),
        user_id=UUID(record.user_id),
        name=record.name,
        revision=revision,
        parent_dataset_ids=dataset.parent_dataset_ids,
        case_count=record.case_count,
        decision_labels=labels,
        extraction_label_count=sum(_has_extraction_labels(case) for case in dataset.cases),
        ready_for_comparison=ready,
        created_at=record.created_at,
    )


def _case_identity(case: EvaluationCase) -> str:
    return str(case.source_analysis_id) if case.source_analysis_id is not None else case.case_id


def _case_contract(case: EvaluationCase) -> dict:
    return {
        "opportunity": case.opportunity.model_dump(mode="json"),
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
        "expected_hard_constraint_breach": case.expected_hard_constraint_breach,
    }


def _merge_cases(datasets: list[EvaluationDataset]) -> list[EvaluationCase]:
    merged: list[EvaluationCase] = []
    by_identity: dict[str, EvaluationCase] = {}
    for dataset in datasets:
        for case in dataset.cases:
            identity = _case_identity(case)
            existing = by_identity.get(identity)
            if existing is None:
                by_identity[identity] = case
                merged.append(case)
                continue
            if _case_contract(existing) != _case_contract(case):
                raise EvaluationDatasetEmptyError(
                    f"The frozen case {case.name!r} has conflicting labels across the selected snapshots."
                )
    return merged


def _source_input(opportunity: OpportunityRecord, extracted: object) -> OpportunityInput:
    stored = opportunity.opportunity_json.get("_source_input")
    if isinstance(stored, dict):
        try:
            return OpportunityInput.model_validate(stored)
        except ValueError:
            pass
    company_name = getattr(extracted, "company_name", None)
    return OpportunityInput(
        source_url=opportunity.source_url,
        raw_text=opportunity.raw_text,
        company_hint=company_name,
    )


class EvaluationStoreMixin:
    """Persistence methods for immutable, user-labelled evaluation snapshots."""

    def _evaluation_rows(self, user_id: UUID) -> list[tuple]:
        return self._session.execute(
            select(BehaviourEventRecord, AnalysisRunRecord, OpportunityRecord)
            .join(
                AnalysisRunRecord,
                BehaviourEventRecord.analysis_run_id == AnalysisRunRecord.id,
            )
            .join(
                OpportunityRecord,
                AnalysisRunRecord.opportunity_id == OpportunityRecord.id,
            )
            .where(
                BehaviourEventRecord.user_id == str(user_id),
                BehaviourEventRecord.explicit.is_(True),
                BehaviourEventRecord.analysis_run_id.is_not(None),
            )
            .order_by(BehaviourEventRecord.created_at.desc())
        ).all()

    def _active_dataset_records(
        self,
        user_id: UUID,
        *,
        name: str | None = None,
    ) -> list[EvaluationDatasetRecord]:
        records = self._session.scalars(
            select(EvaluationDatasetRecord).where(
                EvaluationDatasetRecord.user_id == str(user_id),
                EvaluationDatasetRecord.status == "active",
            )
        ).all()
        if name is None:
            return list(records)
        normalised = _normalise_dataset_name(name)
        return [record for record in records if _normalise_dataset_name(record.name) == normalised]

    def _current_profile(self, user_id: UUID) -> PersonalProfile:
        profile_record = self._session.scalar(
            select(PersonalProfileRecord).where(PersonalProfileRecord.user_id == str(user_id))
        )
        if profile_record is None:
            from opportunityos.infrastructure.database.store import ProfileNotFoundError

            raise ProfileNotFoundError(str(user_id))
        return PersonalProfile.model_validate(profile_record.profile_json)

    def _next_revision(self, user_id: UUID, name: str) -> int:
        return len(self._active_dataset_records(user_id, name=name)) + 1

    def _persist_dataset(self, user_id: UUID, dataset: EvaluationDataset) -> EvaluationDataset:
        decision_labels = Counter(case.expected_decision.value for case in dataset.cases)
        record = EvaluationDatasetRecord(
            id=str(dataset.dataset_id),
            user_id=str(user_id),
            name=dataset.name,
            dataset_json=dataset.model_dump(mode="json"),
            case_count=len(dataset.cases),
            decision_labels_json=dict(decision_labels),
            frozen=True,
            status="active",
        )
        self._session.add(record)
        self._session.flush()
        return dataset

    def _previous_dataset_memberships(self, user_id: UUID) -> dict[str, list[str]]:
        memberships: dict[str, list[str]] = defaultdict(list)
        for record in self._active_dataset_records(user_id):
            dataset = EvaluationDataset.model_validate(record.dataset_json)
            for case in dataset.cases:
                if case.source_analysis_id is None:
                    continue
                memberships[str(case.source_analysis_id)].append(record.name)
        return dict(memberships)

    def list_evaluation_candidates(self, user_id: UUID) -> list[EvaluationCandidate]:
        self._current_profile(user_id)
        previous_memberships = self._previous_dataset_memberships(user_id)
        candidates: list[EvaluationCandidate] = []
        seen_analysis_ids: set[str] = set()
        for event, run, opportunity in self._evaluation_rows(user_id):
            if run.id in seen_analysis_ids:
                continue
            seen_analysis_ids.add(run.id)
            action = _feedback_action(event.event_type)
            expected = _FEEDBACK_TO_DECISION.get(action) if action is not None else None
            if expected is None:
                continue
            stored_result = AnalysisResult.model_validate(run.result_json)
            extracted = stored_result.opportunity
            previous_dataset_names = previous_memberships.get(run.id, [])
            candidates.append(
                EvaluationCandidate(
                    case_id=f"analysis-{run.id}",
                    name=f"{extracted.company_name} — {extracted.title}",
                    opportunity=_source_input(opportunity, extracted),
                    expected_decision=expected,
                    source_analysis_id=UUID(run.id),
                    label_action=action,
                    label_reasons=_feedback_reasons(event.event_json),
                    current_extraction=ExtractionExpectation(
                        company_name=extracted.company_name,
                        title=extracted.title,
                        opportunity_type=extracted.opportunity_type,
                        location=extracted.location,
                        remote_allowed=extracted.remote_allowed,
                        required_skills=extracted.required_skills,
                        problem_areas=extracted.problem_areas,
                        responsibilities=extracted.responsibilities,
                    ),
                    previously_frozen=bool(previous_dataset_names),
                    previous_dataset_names=previous_dataset_names,
                )
            )
        return candidates

    def _new_cases_from_labels(
        self,
        user_id: UUID,
        labels: list[EvaluationCaseLabel],
    ) -> list[EvaluationCase]:
        if not labels:
            raise EvaluationDatasetEmptyError("Select at least one new reviewed opportunity.")
        label_map = {str(item.source_analysis_id): item.expected for item in labels}
        candidates = self.list_evaluation_candidates(user_id)
        candidates_by_id = {str(item.source_analysis_id): item for item in candidates}
        unknown_ids = sorted(set(label_map) - set(candidates_by_id))
        if unknown_ids:
            raise EvaluationDatasetEmptyError(
                "One or more reviewed analyses are no longer available for evaluation. Refresh the candidates."
            )
        reused = [
            candidates_by_id[analysis_id]
            for analysis_id in label_map
            if candidates_by_id[analysis_id].previously_frozen
        ]
        if reused:
            names = ", ".join(item.name for item in reused[:3])
            raise EvaluationDatasetEmptyError(
                f"These cases already belong to a frozen snapshot: {names}. Extend or merge the snapshot instead."
            )

        cases: list[EvaluationCase] = []
        for analysis_id in label_map:
            candidate = candidates_by_id[analysis_id]
            expected_extraction = label_map[analysis_id]
            cases.append(
                EvaluationCase(
                    case_id=candidate.case_id,
                    name=candidate.name,
                    opportunity=candidate.opportunity,
                    expected_decision=candidate.expected_decision,
                    expected_company_name=expected_extraction.company_name,
                    expected_title=expected_extraction.title,
                    expected_opportunity_type=expected_extraction.opportunity_type,
                    expected_location=expected_extraction.location,
                    expected_remote_allowed=expected_extraction.remote_allowed,
                    expected_required_skills=expected_extraction.required_skills,
                    expected_problem_areas=expected_extraction.problem_areas,
                    expected_responsibilities=expected_extraction.responsibilities,
                    source_analysis_id=candidate.source_analysis_id,
                    label_action=candidate.label_action,
                    label_reasons=candidate.label_reasons,
                    notes="Frozen as a new out-of-sample case after user review of decision and extraction labels.",
                )
            )
        return cases

    def create_evaluation_dataset(
        self,
        user_id: UUID,
        name: str,
        extraction_labels: list[EvaluationCaseLabel] | None = None,
    ) -> EvaluationDataset:
        profile = self._current_profile(user_id)
        labels = extraction_labels or []
        if labels and self._active_dataset_records(user_id, name=name):
            raise EvaluationDatasetEmptyError(
                f"A frozen dataset named {name!r} already exists. Use Extend for new cases or Combine for existing snapshots."
            )

        if labels:
            cases = self._new_cases_from_labels(user_id, labels)
        else:
            candidates = self.list_evaluation_candidates(user_id)
            cases = [
                EvaluationCase(
                    case_id=candidate.case_id,
                    name=candidate.name,
                    opportunity=candidate.opportunity,
                    expected_decision=candidate.expected_decision,
                    source_analysis_id=candidate.source_analysis_id,
                    label_action=candidate.label_action,
                    label_reasons=candidate.label_reasons,
                    notes="Frozen from the latest explicit decision feedback; extraction was not labelled.",
                )
                for candidate in candidates
            ]

        if not cases:
            raise EvaluationDatasetEmptyError(
                "No explicitly decided analyses are available. Analyse and decide opportunities before creating a dataset."
            )

        dataset = EvaluationDataset(
            name=name,
            revision=self._next_revision(user_id, name),
            profile=profile,
            cases=cases,
        )
        return self._persist_dataset(user_id, dataset)

    def extend_evaluation_dataset(
        self,
        user_id: UUID,
        dataset_id: UUID,
        extraction_labels: list[EvaluationCaseLabel],
    ) -> EvaluationDataset:
        base = self.get_evaluation_dataset(user_id, dataset_id)
        new_cases = self._new_cases_from_labels(user_id, extraction_labels)
        cases = _merge_cases([base, EvaluationDataset(name=base.name, profile=base.profile, cases=new_cases)])
        dataset = EvaluationDataset(
            name=base.name,
            revision=self._next_revision(user_id, base.name),
            parent_dataset_ids=[dataset_id],
            profile=self._current_profile(user_id),
            cases=cases,
            source="extended_frozen_dataset",
        )
        return self._persist_dataset(user_id, dataset)

    def merge_evaluation_datasets(
        self,
        user_id: UUID,
        source_dataset_ids: list[UUID],
    ) -> EvaluationDataset:
        unique_ids = list(dict.fromkeys(source_dataset_ids))
        if len(unique_ids) < 2:
            raise EvaluationDatasetEmptyError("Select at least two different frozen snapshots to combine.")
        datasets = [self.get_evaluation_dataset(user_id, dataset_id) for dataset_id in unique_ids]
        names = {_normalise_dataset_name(dataset.name) for dataset in datasets}
        if len(names) != 1:
            raise EvaluationDatasetEmptyError(
                "Only snapshots with the same benchmark name can be combined into one revision."
            )
        merged_cases = _merge_cases(datasets)
        if len(merged_cases) <= max(len(dataset.cases) for dataset in datasets):
            raise EvaluationDatasetEmptyError(
                "The selected snapshots do not add any distinct cases to one another."
            )
        name = datasets[0].name
        dataset = EvaluationDataset(
            name=name,
            revision=self._next_revision(user_id, name),
            parent_dataset_ids=unique_ids,
            profile=self._current_profile(user_id),
            cases=merged_cases,
            source="merged_frozen_datasets",
        )
        return self._persist_dataset(user_id, dataset)

    def list_evaluation_datasets(
        self,
        user_id: UUID,
        *,
        include_history: bool = False,
    ) -> list[EvaluationDatasetSummary]:
        records = sorted(
            self._active_dataset_records(user_id),
            key=lambda record: record.created_at,
        )
        revisions: dict[str, int] = defaultdict(int)
        summaries: list[EvaluationDatasetSummary] = []
        for record in records:
            key = _normalise_dataset_name(record.name)
            revisions[key] += 1
            summaries.append(_dataset_summary(record, revisions[key]))
        if include_history:
            return list(reversed(summaries))

        latest_by_name: dict[str, EvaluationDatasetSummary] = {}
        for summary in summaries:
            latest_by_name[_normalise_dataset_name(summary.name)] = summary
        return sorted(latest_by_name.values(), key=lambda item: item.created_at, reverse=True)

    def get_evaluation_dataset(self, user_id: UUID, dataset_id: UUID) -> EvaluationDataset:
        record = self._session.scalar(
            select(EvaluationDatasetRecord).where(
                EvaluationDatasetRecord.id == str(dataset_id),
                EvaluationDatasetRecord.user_id == str(user_id),
                EvaluationDatasetRecord.status == "active",
            )
        )
        if record is None:
            raise EvaluationDatasetNotFoundError(str(dataset_id))
        return EvaluationDataset.model_validate(record.dataset_json)

    def save_evaluation_run(self, report: EvaluationReport) -> EvaluationReport:
        record = EvaluationRunRecord(
            id=str(report.run_id),
            dataset_id=str(report.dataset_id),
            user_id=str(report.user_id),
            mode=report.mode,
            provider_order=report.provider_order,
            report_json=report.model_dump(mode="json"),
            status="completed",
        )
        self._session.add(record)
        self._session.flush()
        return report

    def list_evaluation_runs(self, user_id: UUID, dataset_id: UUID) -> list[EvaluationRunSummary]:
        records = self._session.scalars(
            select(EvaluationRunRecord)
            .where(
                EvaluationRunRecord.user_id == str(user_id),
                EvaluationRunRecord.dataset_id == str(dataset_id),
                EvaluationRunRecord.status == "completed",
            )
            .order_by(EvaluationRunRecord.created_at.desc())
        ).all()
        return [
            EvaluationRunSummary(
                run_id=UUID(record.id),
                dataset_id=UUID(record.dataset_id),
                mode=record.mode,
                provider_order=record.provider_order,
                decision_accuracy=float(record.report_json["metrics"]["decision_accuracy"]),
                false_pursue_rate=float(record.report_json["metrics"]["false_pursue_rate"]),
                case_count=int(record.report_json["metrics"]["case_count"]),
                created_at=record.created_at,
            )
            for record in records
        ]

    def get_evaluation_run(
        self,
        user_id: UUID,
        dataset_id: UUID,
        run_id: UUID,
    ) -> EvaluationReport:
        record = self._session.scalar(
            select(EvaluationRunRecord).where(
                EvaluationRunRecord.id == str(run_id),
                EvaluationRunRecord.dataset_id == str(dataset_id),
                EvaluationRunRecord.user_id == str(user_id),
            )
        )
        if record is None:
            raise EvaluationRunNotFoundError(str(run_id))
        return EvaluationReport.model_validate(record.report_json)
