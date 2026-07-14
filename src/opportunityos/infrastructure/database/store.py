from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from opportunityos.domain.enums import Decision
from opportunityos.domain.models import (
    AnalysisResult,
    FeedbackEvent,
    OpportunityInput,
    PersonalProfile,
)
from opportunityos.infrastructure.database.models import (
    AnalysisRunRecord,
    BehaviourEventRecord,
    CompanyRecord,
    EvidenceClaimRecord,
    MemoryItemRecord,
    OpportunityRecord,
    PersonalProfileRecord,
    User,
)


class ProfileNotFoundError(LookupError):
    pass


class AnalysisNotFoundError(LookupError):
    pass


class SqlAlchemyStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_profile(self, profile: PersonalProfile, *, email: str | None = None) -> PersonalProfile:
        user_id = str(profile.user_id)
        user = self._session.get(User, user_id)
        if user is None:
            user = User(id=user_id, email=email, display_name=profile.display_name)
            self._session.add(user)
        else:
            user.display_name = profile.display_name
            if email is not None:
                user.email = email

        record = self._session.scalar(
            select(PersonalProfileRecord).where(PersonalProfileRecord.user_id == user_id)
        )
        payload = profile.model_dump(mode="json")
        if record is None:
            record = PersonalProfileRecord(
                user_id=user_id,
                headline=profile.headline,
                profile_json=payload,
                version=1,
            )
            self._session.add(record)
        else:
            record.headline = profile.headline
            record.profile_json = payload
            record.version += 1

        self._replace_profile_memory(profile)
        self._session.flush()
        return profile

    def _replace_profile_memory(self, profile: PersonalProfile) -> None:
        user_id = str(profile.user_id)
        self._session.execute(delete(MemoryItemRecord).where(MemoryItemRecord.user_id == user_id))

        for preference in profile.preferences:
            self._session.add(
                MemoryItemRecord(
                    user_id=user_id,
                    category="preference",
                    key=preference.key,
                    value_json=preference.model_dump(mode="json"),
                    source="explicit" if preference.explicit else "inferred",
                    confidence=preference.confidence,
                    expires_at=None,
                    is_user_overridden=preference.explicit,
                )
            )
        for constraint in profile.constraints:
            self._session.add(
                MemoryItemRecord(
                    user_id=user_id,
                    category="constraint",
                    key=constraint.key,
                    value_json=constraint.model_dump(mode="json"),
                    source="explicit",
                    confidence=1.0,
                    expires_at=None,
                    is_user_overridden=True,
                )
            )
        for aspiration in profile.aspirations:
            self._session.add(
                MemoryItemRecord(
                    user_id=user_id,
                    category="aspiration",
                    key=aspiration.name,
                    value_json=aspiration.model_dump(mode="json"),
                    source="explicit",
                    confidence=aspiration.weight,
                    expires_at=None,
                    is_user_overridden=True,
                )
            )

    def get_profile(self, user_id: UUID) -> PersonalProfile:
        record = self._session.scalar(
            select(PersonalProfileRecord).where(PersonalProfileRecord.user_id == str(user_id))
        )
        if record is None:
            raise ProfileNotFoundError(str(user_id))
        return PersonalProfile.model_validate(record.profile_json)

    def save_analysis(
        self,
        profile: PersonalProfile,
        source: OpportunityInput,
        result: AnalysisResult,
    ) -> AnalysisResult:
        company = CompanyRecord(
            name=result.opportunity.company_name,
            website=str(source.source_url) if source.source_url else None,
            company_json={"name": result.opportunity.company_name},
        )
        self._session.add(company)
        self._session.flush()

        opportunity = OpportunityRecord(
            id=str(result.opportunity.id),
            user_id=str(profile.user_id),
            company_id=company.id,
            source_url=str(source.source_url) if source.source_url else None,
            raw_text=source.raw_text,
            opportunity_json=result.opportunity.model_dump(mode="json"),
            status=result.recommendation.decision.value,
        )
        self._session.add(opportunity)
        self._session.flush()

        for evidence in result.opportunity.evidence:
            self._session.add(
                EvidenceClaimRecord(
                    id=str(evidence.id),
                    opportunity_id=opportunity.id,
                    claim=evidence.claim,
                    claim_type=evidence.claim_type.value,
                    source_url=str(evidence.source_url) if evidence.source_url else None,
                    supporting_excerpt=evidence.supporting_excerpt,
                    confidence=evidence.confidence,
                )
            )

        run = AnalysisRunRecord(
            id=str(result.analysis_id),
            user_id=str(profile.user_id),
            opportunity_id=opportunity.id,
            orchestrator=result.orchestrator,
            model_metadata_json=result.model_metadata,
            result_json=result.model_dump(mode="json"),
            status="completed",
        )
        self._session.add(run)
        self._session.flush()
        return result

    def get_analysis(self, user_id: UUID, analysis_id: UUID) -> AnalysisResult:
        record = self._session.scalar(
            select(AnalysisRunRecord).where(
                AnalysisRunRecord.id == str(analysis_id),
                AnalysisRunRecord.user_id == str(user_id),
            )
        )
        if record is None:
            raise AnalysisNotFoundError(str(analysis_id))
        return AnalysisResult.model_validate(record.result_json)

    def record_feedback(
        self,
        profile: PersonalProfile,
        feedback: FeedbackEvent,
        applied_updates: list[str],
    ) -> None:
        analysis = self._session.scalar(
            select(AnalysisRunRecord).where(
                AnalysisRunRecord.id == str(feedback.analysis_id),
                AnalysisRunRecord.user_id == str(profile.user_id),
            )
        )
        if analysis is None:
            raise AnalysisNotFoundError(str(feedback.analysis_id))

        self._session.add(
            BehaviourEventRecord(
                id=str(feedback.event_id),
                user_id=str(profile.user_id),
                analysis_run_id=str(feedback.analysis_id),
                event_type=feedback.action.value,
                event_json={
                    **feedback.model_dump(mode="json"),
                    "applied_updates": applied_updates,
                },
                explicit=feedback.explicit,
            )
        )
        self.save_profile(profile)

    def get_analysis_opportunity_type(self, user_id: UUID, analysis_id: UUID) -> str | None:
        run = self._session.scalar(
            select(AnalysisRunRecord).where(
                AnalysisRunRecord.id == str(analysis_id),
                AnalysisRunRecord.user_id == str(user_id),
            )
        )
        if run is None:
            return None
        opportunity = self._session.get(OpportunityRecord, run.opportunity_id)
        if opportunity is None:
            return None
        return opportunity.opportunity_json.get("opportunity_type")

    def count_user_analyses(self, user_id: UUID) -> int:
        count = self._session.scalar(
            select(func.count()).select_from(AnalysisRunRecord).where(
                AnalysisRunRecord.user_id == str(user_id)
            )
        )
        return int(count or 0)

    def update_opportunity_status(self, analysis_id: UUID, decision: Decision) -> None:
        run = self._session.get(AnalysisRunRecord, str(analysis_id))
        if run is None:
            raise AnalysisNotFoundError(str(analysis_id))
        opportunity = self._session.get(OpportunityRecord, run.opportunity_id)
        if opportunity is not None:
            opportunity.status = decision.value
