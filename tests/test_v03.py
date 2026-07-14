from uuid import uuid4

from fastapi.testclient import TestClient

from opportunityos.api.main import app
from opportunityos.application.learning import apply_feedback
from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.enums import FeedbackAction, MemoryAction, MemoryCategory, MemoryStatus, OpportunityType
from opportunityos.domain.models import (
    AnalysisRequest,
    FeedbackEvent,
    MemoryMutationRequest,
    OpportunityInput,
    OpportunityProfile,
    OutreachDraft,
    PersonalProfile,
    WeightedPreference,
)
from opportunityos.infrastructure.database import Database, SqlAlchemyStore
from opportunityos.infrastructure.llm.mock import MockBusinessAnalyst, MockOpportunityExtractor, MockOutreachWriter
from opportunityos.infrastructure.research import InputOnlyResearchProvider


class UnsupportedWriter:
    def draft(self, profile: PersonalProfile, opportunity: OpportunityProfile, hypotheses: list) -> OutreachDraft:
        return OutreachDraft(body="Your margins are falling and your team needs urgent help.")


def _service(writer: object = None) -> AnalyseOpportunityService:
    return AnalyseOpportunityService(
        research=InputOnlyResearchProvider(),
        extractor=MockOpportunityExtractor(),
        analyst=MockBusinessAnalyst(),
        outreach_writer=writer or MockOutreachWriter(),
    )


def _opportunity() -> OpportunityInput:
    return OpportunityInput(
        raw_text=(
            "Company: Acme Consumer\nRole: Fractional Data and AI Lead\nLocation: Remote\n"
            "Need product analytics, retention and AI support."
        )
    )


def test_critic_passes_grounded_outreach_and_blocks_unsupported_claims(strong_profile: PersonalProfile) -> None:
    grounded = _service().execute(AnalysisRequest(profile=strong_profile, opportunity=_opportunity()))
    assert grounded.critic.passed is True
    assert grounded.outreach is not None

    blocked = _service(UnsupportedWriter()).execute(AnalysisRequest(profile=strong_profile, opportunity=_opportunity()))
    assert blocked.critic.block_outreach is True
    assert blocked.critic.blocked_draft is not None
    assert blocked.outreach is None


def test_implicit_learning_cannot_override_explicit_preference(strong_profile: PersonalProfile) -> None:
    strong_profile.preferences.append(
        WeightedPreference(key="engagement:fractional", weight=0.9, explicit=True, confidence=1.0)
    )
    feedback = FeedbackEvent(analysis_id=uuid4(), action=FeedbackAction.REJECT, explicit=False)
    updated, changes = apply_feedback(strong_profile, feedback, opportunity_type=OpportunityType.FRACTIONAL)
    preference = next(item for item in updated.preferences if item.key == "engagement:fractional")
    assert preference.weight == 0.9
    assert "Preserved explicit engagement:fractional" in changes


def test_memory_can_be_confirmed_rejected_and_audited(strong_profile: PersonalProfile) -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    with database.session() as session:
        store = SqlAlchemyStore(session)
        store.save_profile(strong_profile)
        memories = store.list_memory(strong_profile.user_id)
        capability = next(
            item
            for item in memories
            if item.category == MemoryCategory.CAPABILITY and item.key == "product analytics"
        )
        confirmed = store.mutate_memory(
            strong_profile.user_id,
            capability.id,
            MemoryMutationRequest(action=MemoryAction.CONFIRM),
        )
        assert confirmed.status == MemoryStatus.CONFIRMED
        retention = next(item for item in store.list_memory(strong_profile.user_id) if item.key == "retention")
        rejected = store.mutate_memory(
            strong_profile.user_id,
            retention.id,
            MemoryMutationRequest(action=MemoryAction.REJECT),
        )
        assert rejected.active is False
        actions = {item.action for item in store.list_memory_audit(strong_profile.user_id)}
        assert {"created", "confirm", "reject"} <= actions


def test_memory_api_exposes_controls_and_audit() -> None:
    client = TestClient(app)
    onboarding = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Memory API User",
            "headline": "Data and AI lead",
            "resume_text": "Senior data scientist with product analytics, retention, Python and SQL experience.",
        },
    )
    assert onboarding.status_code == 201
    user_id = onboarding.json()["profile"]["user_id"]
    memory = client.get(f"/v1/users/{user_id}/memory")
    assert memory.status_code == 200
    capability = next(item for item in memory.json()["items"] if item["category"] == "capability")
    confirmed = client.patch(
        f"/v1/users/{user_id}/memory/{capability['id']}",
        json={"action": "confirm", "reason": "user verified"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    audit = client.get(f"/v1/users/{user_id}/memory-audit")
    assert audit.status_code == 200
    assert any(item["action"] == "confirm" for item in audit.json()["events"])
