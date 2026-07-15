from __future__ import annotations

from opportunityos.application.grounding import ground_extracted_opportunity
from opportunityos.application.guardrails import evaluate_guardrails
from opportunityos.domain.enums import Decision, EvidenceType, OpportunityType
from opportunityos.domain.models import (
    BusinessHypothesis,
    EvidenceClaim,
    OpportunityInput,
    OpportunityProfile,
    Recommendation,
)


def _evidence() -> EvidenceClaim:
    return EvidenceClaim(
        claim="Dream Cricket is hiring a Senior Product Manager for a consulting engagement.",
        claim_type=EvidenceType.OBSERVED_FACT,
        supporting_excerpt=(
            "Senior Product Manager consulting role requiring product management, gaming experience, "
            "stakeholder communication, analytics and AI-enabled products."
        ),
        confidence=0.95,
    )


def test_grounding_removes_unsupported_extracted_facts_before_scoring() -> None:
    evidence = _evidence()
    source = OpportunityInput(
        company_hint="Dream Cricket",
        raw_text=evidence.supporting_excerpt,
    )
    extracted = OpportunityProfile(
        company_name="Invented Holdings",
        title="Senior Product Manager",
        opportunity_type=OpportunityType.CONSULTING,
        location="Singapore",
        seniority="senior",
        compensation_text="$250,000",
        required_skills=["product management", "quantum computing"],
        responsibilities=["stakeholder communication", "manage a nuclear facility"],
        problem_areas=["analytics", "satellite propulsion"],
        evidence=[],
        extraction_confidence=0.9,
    )

    grounded, issues = ground_extracted_opportunity(source, [evidence], extracted)

    assert grounded.company_name == "Dream Cricket"
    assert grounded.location is None
    assert grounded.compensation_text is None
    assert "product management" in grounded.required_skills
    assert "quantum computing" not in grounded.required_skills
    assert "manage a nuclear facility" not in grounded.responsibilities
    assert "satellite propulsion" not in grounded.problem_areas
    assert grounded.evidence == [evidence]
    assert any(item.code == "unsupported_extracted_field" for item in issues)
    assert any(item.code == "unsupported_extracted_value" for item in issues)


def test_guardrails_block_hypothesis_whose_citation_does_not_support_wording() -> None:
    evidence = _evidence()
    opportunity = OpportunityProfile(
        company_name="Dream Cricket",
        title="Senior Product Manager",
        opportunity_type=OpportunityType.CONSULTING,
        evidence=[evidence],
        extraction_confidence=0.9,
    )
    hypothesis = BusinessHypothesis(
        statement="Dream Cricket is suffering a severe cash-flow crisis.",
        claim_type=EvidenceType.SUPPORTED_INFERENCE,
        rationale="This is not present in the role description.",
        evidence_ids=[evidence.id],
        confidence=0.8,
    )
    recommendation = Recommendation(
        decision=Decision.HOLD,
        rationale="More evidence is required.",
        next_action="Collect more evidence.",
    )

    critic = evaluate_guardrails(opportunity, [hypothesis], recommendation, None)

    assert critic.passed is False
    assert any(item.code == "evidence_claim_mismatch" for item in critic.issues)
