from uuid import uuid4

from fastapi.testclient import TestClient

from opportunityos.api.main import app
from opportunityos.application.learning import apply_feedback
from opportunityos.application.scoring import (
    GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY,
    GATE_JUNIOR_EXECUTION_ONLY,
    decision_trace,
    recommend,
)
from opportunityos.domain.enums import Decision, FeedbackAction, FeedbackReason, OpportunityType
from opportunityos.domain.models import (
    Capability,
    FeedbackEvent,
    FitScore,
    OpportunityProfile,
    PersonalProfile,
    ScoreDimension,
)


def _profile() -> PersonalProfile:
    return PersonalProfile(
        display_name="Gate Test User",
        headline="Fractional Data and AI leader",
        capabilities=[Capability(name="data science", proficiency=0.9)],
    )


def _fit(total: int) -> FitScore:
    return FitScore(
        total=total,
        dimensions=[
            ScoreDimension(
                name="test",
                score=total / 100,
                weight=1.0,
                explanation="Controlled test score.",
            )
        ],
    )


def test_vague_high_scoring_signal_is_capped_at_hold() -> None:
    profile = _profile()
    opportunity = OpportunityProfile(
        company_name="Ethos",
        title="Opportunity at Ethos",
        opportunity_type=OpportunityType.UNKNOWN,
        extraction_confidence=0.9,
    )

    score_decision, gates, final_decision = decision_trace(profile, _fit(80), opportunity)
    recommendation = recommend(_fit(80), opportunity, profile)

    assert score_decision == Decision.PURSUE
    assert GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY in gates
    assert final_decision == Decision.HOLD
    assert recommendation.decision == Decision.HOLD
    assert "concrete role or engagement" in recommendation.rationale


def test_generated_advisory_title_is_still_insufficient_identity() -> None:
    profile = _profile()
    opportunity = OpportunityProfile(
        company_name="Ethos",
        title="Advisory opportunity",
        opportunity_type=OpportunityType.ADVISORY,
        extraction_confidence=0.9,
    )

    score_decision, gates, final_decision = decision_trace(profile, _fit(76), opportunity)

    assert score_decision == Decision.PURSUE
    assert GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY in gates
    assert final_decision == Decision.HOLD


def test_junior_execution_only_role_is_rejected_even_when_score_clears_hold() -> None:
    profile = _profile()
    opportunity = OpportunityProfile(
        company_name="genbrothers",
        title="Data Analyst (Excel Power Query)",
        opportunity_type=OpportunityType.FULL_TIME,
        required_skills=["Excel", "Power Query"],
        responsibilities=["Excel reporting", "dashboard production", "report generation"],
        extraction_confidence=0.9,
    )

    score_decision, gates, final_decision = decision_trace(profile, _fit(62), opportunity)

    assert score_decision == Decision.HOLD
    assert GATE_JUNIOR_EXECUTION_ONLY in gates
    assert final_decision == Decision.REJECT
    assert recommend(_fit(62), opportunity, profile).decision == Decision.REJECT


def test_negative_reasons_learn_specific_aversions_without_broad_engagement_penalty() -> None:
    profile = _profile()
    feedback = FeedbackEvent(
        analysis_id=uuid4(),
        action=FeedbackAction.REJECT,
        reasons=[
            FeedbackReason.TOO_JUNIOR,
            FeedbackReason.TOO_EXECUTION_HEAVY,
            FeedbackReason.LOW_OWNERSHIP,
        ],
        explicit=True,
    )

    updated, changes = apply_feedback(
        profile,
        feedback,
        opportunity_type=OpportunityType.FULL_TIME,
    )

    weights = {item.key: item.weight for item in updated.preferences}
    assert weights["seniority:junior"] < 0.5
    assert weights["work_style:execution_only"] < 0.5
    assert weights["work_style:low_ownership"] < 0.5
    assert "engagement:full_time" not in weights
    assert len(changes) == 3


def test_web_shell_contains_reason_aware_feedback_controls() -> None:
    response = TestClient(app).get("/app/")

    assert response.status_code == 200
    assert 'id="feedback-dialog"' in response.text
    assert 'value="missing_information"' in response.text
    assert 'value="low_ownership"' in response.text
