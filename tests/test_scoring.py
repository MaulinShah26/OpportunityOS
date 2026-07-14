from opportunityos.application.scoring import calculate_fit, recommend
from opportunityos.domain.enums import Decision, EvidenceType, OpportunityType
from opportunityos.domain.models import EvidenceClaim, OpportunityProfile, PersonalProfile


def test_strong_relevant_opportunity_scores_high(strong_profile: PersonalProfile) -> None:
    opportunity = OpportunityProfile(
        company_name="Acme",
        title="Fractional Data and AI Lead",
        opportunity_type=OpportunityType.FRACTIONAL,
        location="Remote",
        remote_allowed=True,
        required_skills=["product analytics", "retention", "ai"],
        responsibilities=["product analytics", "retention"],
        problem_areas=["retention", "ai"],
        evidence=[
            EvidenceClaim(
                claim="Role description",
                claim_type=EvidenceType.OBSERVED_FACT,
                supporting_excerpt="Fractional data and AI lead",
                confidence=0.95,
            )
            for _ in range(4)
        ],
        extraction_confidence=0.9,
    )
    fit = calculate_fit(strong_profile, opportunity)
    assert fit.total >= 72
    assert recommend(fit, opportunity).decision == Decision.PURSUE


def test_hard_constraint_forces_rejection(strong_profile: PersonalProfile) -> None:
    opportunity = OpportunityProfile(
        company_name="Acme",
        title="Data Lead",
        opportunity_type=OpportunityType.FULL_TIME,
        location="Mumbai",
        remote_allowed=False,
        required_skills=["product analytics", "retention", "ai"],
        responsibilities=["product analytics"],
        problem_areas=["retention"],
        extraction_confidence=0.9,
    )
    fit = calculate_fit(strong_profile, opportunity)
    result = recommend(fit, opportunity)
    assert fit.total == 0
    assert result.decision == Decision.REJECT
    assert fit.hard_constraint_breaches
