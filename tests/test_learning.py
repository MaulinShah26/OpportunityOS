from uuid import uuid4

from opportunityos.application.learning import apply_feedback
from opportunityos.domain.enums import FeedbackAction, FeedbackReason, OpportunityType
from opportunityos.domain.models import FeedbackEvent, PersonalProfile


def test_explicit_positive_feedback_increases_engagement_preference(
    strong_profile: PersonalProfile,
) -> None:
    before = next(p.weight for p in strong_profile.preferences if p.key == "fractional")
    feedback = FeedbackEvent(
        analysis_id=uuid4(),
        action=FeedbackAction.PURSUE,
        reasons=[FeedbackReason.STRONG_FIT],
        explicit=True,
    )
    updated, changes = apply_feedback(
        strong_profile,
        feedback,
        opportunity_type=OpportunityType.FRACTIONAL,
    )
    after = next(p.weight for p in updated.preferences if p.key == "engagement:fractional")
    assert after > 0.5
    assert before == 0.95
    assert changes


def test_implicit_feedback_has_smaller_effect(strong_profile: PersonalProfile) -> None:
    explicit = FeedbackEvent(analysis_id=uuid4(), action=FeedbackAction.REJECT, explicit=True)
    implicit = FeedbackEvent(analysis_id=uuid4(), action=FeedbackAction.REJECT, explicit=False)
    explicit_profile, _ = apply_feedback(
        strong_profile, explicit, opportunity_type=OpportunityType.CONTRACT
    )
    implicit_profile, _ = apply_feedback(
        strong_profile, implicit, opportunity_type=OpportunityType.CONTRACT
    )
    explicit_weight = next(
        p.weight for p in explicit_profile.preferences if p.key == "engagement:contract"
    )
    implicit_weight = next(
        p.weight for p in implicit_profile.preferences if p.key == "engagement:contract"
    )
    assert explicit_weight < implicit_weight
