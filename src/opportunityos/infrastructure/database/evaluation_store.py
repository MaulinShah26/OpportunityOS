from __future__ import annotations

from collections import Counter
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


def _has_extraction_labels(case: EvaluationCase) -> bool:
    return any(
        [
            case.expected_company_name,
            case.expected_title,
            case.expected_opportunity_type is not None,
            case.expected_remote_allowed is not None,
            case.expected_required_skills,
            case.expected_problem_areas,
        ]
    )


def _dataset_summary(record: EvaluationDatasetRecord) -> EvaluationDatasetSummary:
    labels = {str(key): int(value) for key, value in record.decision_labels_json.items()}
    non_pursue = labels.get(Decision.HOLD.value, 0) + labels.get(Decision.REJECT.value, 0)
    ready = record.case_count >= 5 and labels.get(Decision.PURSUE.value, 0) > 0 and non_pursue > 0
    dataset = EvaluationDataset.model_validate(record.dataset_json)
    return EvaluationDatasetSummary(
        dataset_id=UUID(record.id),
        user_id=UUID(record.user_id),
        name=record.name,
        case_count=record.case_count,
        decision_labels=labels,
        extraction_label_count=sum(_has_extraction_labels(case) for case in dataset.cases),
        ready_for_comparison=ready,
        created_at=record.created_at,
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

    def list_evaluation_candidates(self, user_id: UUID) -> list[EvaluationCandidate]:
        profile_record = self._session.scalar(
            select(PersonalProfileRecord).where(PersonalProfileRecord.user_id == str(user_id))
        )
        if profile_record is None:
            from opportunityos.infrastructure.database.store import ProfileNotFoundError

            raise ProfileNotFoundError(str(user_id))

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
            candidates.append(
                EvaluationCandidate(
                    case_id=f"analysis-{run.id}",
                    name=f"{extracted.company_name} — {extracted.title}",
                    opportunity=OpportunityInput(
                        source_url=opportunity.source_url,
                        raw_text=opportunity.raw_text,
                        company_hint=extracted.company_name,
                    ),
                    expected_decision=expected,
                    source_analysis_id=UUID(run.id),
                    label_action=action,
                    label_reasons=_feedback_reasons(event.event_json),
                    current_extraction=ExtractionExpectation(
                        company_name=extracted.company_name,
                        title=extracted.title,
                        opportunity_type=extracted.opportunity_type,
                        remote_allowed=extracted.remote_allowed,
                        required_skills=extracted.required_skills,
                        problem_areas=extracted.problem_areas,
                    ),
                )
            )
        return candidates

    def create_evaluation_dataset(
        self,
        user_id: UUID,
        name: str,
        extraction_labels: list[EvaluationCaseLabel] | None = None,
    ) -> EvaluationDataset:
        profile_record = self._session.scalar(
            select(PersonalProfileRecord).where(PersonalProfileRecord.user_id == str(user_id))
        )
        if profile_record is None:
            from opportunityos.infrastructure.database.store import ProfileNotFoundError

            raise ProfileNotFoundError(str(user_id))
        profile = PersonalProfile.model_validate(profile_record.profile_json)
        label_map = {str(item.source_analysis_id): item.expected for item in (extraction_labels or [])}

        cases: list[EvaluationCase] = []
        for candidate in self.list_evaluation_candidates(user_id):
            expected_extraction = label_map.get(str(candidate.source_analysis_id))
            cases.append(
                EvaluationCase(
                    case_id=candidate.case_id,
                    name=candidate.name,
                    opportunity=candidate.opportunity,
                    expected_decision=candidate.expected_decision,
                    expected_company_name=(expected_extraction.company_name if expected_extraction else None),
                    expected_title=(expected_extraction.title if expected_extraction else None),
                    expected_opportunity_type=(
                        expected_extraction.opportunity_type if expected_extraction else None
                    ),
                    expected_remote_allowed=(
                        expected_extraction.remote_allowed if expected_extraction else None
                    ),
                    expected_required_skills=(
                        expected_extraction.required_skills if expected_extraction else []
                    ),
                    expected_problem_areas=(
                        expected_extraction.problem_areas if expected_extraction else []
                    ),
                    source_analysis_id=candidate.source_analysis_id,
                    label_action=candidate.label_action,
                    label_reasons=candidate.label_reasons,
                    notes=(
                        "Frozen after user review of decision and extraction labels."
                        if expected_extraction
                        else "Frozen from the latest explicit decision feedback; extraction was not labelled."
                    ),
                )
            )

        if not cases:
            raise EvaluationDatasetEmptyError(
                "No explicitly labelled analyses are available. Mark opportunities as worth pursuing, "
                "save signal, or not relevant before creating a dataset."
            )

        dataset = EvaluationDataset(name=name, profile=profile, cases=cases)
        labels = Counter(case.expected_decision.value for case in cases)
        record = EvaluationDatasetRecord(
            id=str(dataset.dataset_id),
            user_id=str(user_id),
            name=name,
            dataset_json=dataset.model_dump(mode="json"),
            case_count=len(cases),
            decision_labels_json=dict(labels),
            frozen=True,
            status="active",
        )
        self._session.add(record)
        self._session.flush()
        return dataset

    def list_evaluation_datasets(self, user_id: UUID) -> list[EvaluationDatasetSummary]:
        records = self._session.scalars(
            select(EvaluationDatasetRecord)
            .where(
                EvaluationDatasetRecord.user_id == str(user_id),
                EvaluationDatasetRecord.status == "active",
            )
            .order_by(EvaluationDatasetRecord.created_at.desc())
        ).all()
        return [_dataset_summary(record) for record in records]

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
