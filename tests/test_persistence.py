from uuid import uuid4

import pytest

from opportunityos.application.learning import apply_feedback
from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.enums import FeedbackAction, OpportunityType
from opportunityos.domain.models import AnalysisRequest, FeedbackEvent, OpportunityInput, PersonalProfile
from opportunityos.infrastructure.database import AnalysisNotFoundError, Database, SqlAlchemyStore
from opportunityos.infrastructure.llm.mock import MockBusinessAnalyst, MockOpportunityExtractor, MockOutreachWriter
from opportunityos.infrastructure.research import InputOnlyResearchProvider


@pytest.fixture
def database() -> Database:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    return database


def _service() -> AnalyseOpportunityService:
    return AnalyseOpportunityService(
        research=InputOnlyResearchProvider(),
        extractor=MockOpportunityExtractor(),
        analyst=MockBusinessAnalyst(),
        outreach_writer=MockOutreachWriter(),
    )


def test_profile_analysis_and_feedback_are_persisted(database: Database, strong_profile: PersonalProfile) -> None:
    with database.session() as session:
        SqlAlchemyStore(session).save_profile(strong_profile, email="person@example.com")

    with database.session() as session:
        store = SqlAlchemyStore(session)
        loaded = store.get_profile(strong_profile.user_id)
        source = OpportunityInput(raw_text="Company: Acme Consumer\nRole: Fractional Data and AI Lead\nLocation: Remote\nNeed product analytics, retention and AI support.")
        result = _service().execute(AnalysisRequest(profile=loaded, opportunity=source))
        store.save_analysis(loaded, source, result)

    with database.session() as session:
        store = SqlAlchemyStore(session)
        stored_result = store.get_analysis(strong_profile.user_id, result.analysis_id)
        assert stored_result.opportunity.company_name == "Acme Consumer"
        assert store.count_user_analyses(strong_profile.user_id) == 1
        feedback = FeedbackEvent(analysis_id=result.analysis_id, action=FeedbackAction.PURSUE, explicit=True)
        updated, changes = apply_feedback(store.get_profile(strong_profile.user_id), feedback, opportunity_type=OpportunityType.FRACTIONAL)
        store.record_feedback(updated, feedback, changes)

    with database.session() as session:
        refreshed = SqlAlchemyStore(session).get_profile(strong_profile.user_id)
        fractional = next(preference for preference in refreshed.preferences if preference.key == "engagement:fractional")
        assert fractional.weight > 0.5


def test_feedback_rejects_unknown_analysis(database: Database, strong_profile: PersonalProfile) -> None:
    with database.session() as session:
        store = SqlAlchemyStore(session)
        store.save_profile(strong_profile)
        feedback = FeedbackEvent(analysis_id=uuid4(), action=FeedbackAction.REJECT)
        with pytest.raises(AnalysisNotFoundError):
            store.record_feedback(strong_profile, feedback, [])
