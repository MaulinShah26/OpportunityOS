from __future__ import annotations

import re

from opportunityos.domain.enums import EvidenceType, OpportunityType
from opportunityos.domain.models import (
    BusinessHypothesis,
    EvidenceClaim,
    OpportunityInput,
    OpportunityProfile,
    OutreachDraft,
    PersonalProfile,
)


class MockOpportunityExtractor:
    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile:
        text = (source.raw_text or "").strip()
        lowered = text.lower()
        title_match = re.search(r"(?:role|title)\s*:\s*([^\n]+)", text, re.IGNORECASE)
        company_match = re.search(r"(?:company)\s*:\s*([^\n]+)", text, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else "Unspecified opportunity"
        company = (
            company_match.group(1).strip()
            if company_match
            else source.company_hint or "Unknown company"
        )
        if "fractional" in lowered:
            opportunity_type = OpportunityType.FRACTIONAL
        elif "consult" in lowered:
            opportunity_type = OpportunityType.CONSULTING
        elif "contract" in lowered:
            opportunity_type = OpportunityType.CONTRACT
        elif "full-time" in lowered or "full time" in lowered:
            opportunity_type = OpportunityType.FULL_TIME
        else:
            opportunity_type = OpportunityType.UNKNOWN

        known_skills = [
            "data science",
            "analytics",
            "product analytics",
            "retention",
            "growth",
            "ai",
            "machine learning",
            "forecasting",
            "experimentation",
            "python",
        ]
        required_skills = [skill for skill in known_skills if skill in lowered]
        problem_areas = [
            skill
            for skill in ["retention", "growth", "forecasting", "analytics", "ai"]
            if skill in lowered
        ]
        remote = True if "remote" in lowered else False if "onsite" in lowered else None
        location = None
        location_match = re.search(r"location\s*:\s*([^\n]+)", text, re.IGNORECASE)
        if location_match:
            location = location_match.group(1).strip()

        return OpportunityProfile(
            company_name=company,
            title=title,
            opportunity_type=opportunity_type,
            location=location,
            remote_allowed=remote,
            required_skills=required_skills,
            responsibilities=problem_areas,
            problem_areas=problem_areas,
            evidence=evidence,
            extraction_confidence=0.75 if text else 0.4,
        )


class MockBusinessAnalyst:
    def analyse(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
    ) -> list[BusinessHypothesis]:
        hypotheses: list[BusinessHypothesis] = []
        if opportunity.problem_areas:
            hypotheses.append(
                BusinessHypothesis(
                    statement=(
                        f"{opportunity.company_name} may need stronger decision systems around "
                        f"{', '.join(opportunity.problem_areas[:3])}."
                    ),
                    claim_type=EvidenceType.SUPPORTED_INFERENCE,
                    rationale="The opportunity explicitly references these problem areas.",
                    evidence_ids=[item.id for item in opportunity.evidence],
                    confidence=0.65,
                )
            )
        else:
            hypotheses.append(
                BusinessHypothesis(
                    statement="The business need is not sufficiently specified.",
                    claim_type=EvidenceType.SPECULATIVE_HYPOTHESIS,
                    rationale="The source lacks concrete problem or responsibility information.",
                    evidence_ids=[item.id for item in opportunity.evidence],
                    confidence=0.35,
                )
            )
        return hypotheses


class MockOutreachWriter:
    def draft(
        self,
        profile: PersonalProfile,
        opportunity: OpportunityProfile,
        hypotheses: list[BusinessHypothesis],
    ) -> OutreachDraft:
        capability_names = ", ".join(cap.name for cap in profile.capabilities[:3])
        problem = opportunity.problem_areas[0] if opportunity.problem_areas else "the role's core problem"
        return OutreachDraft(
            subject=f"Regarding {opportunity.title} at {opportunity.company_name}",
            body=(
                f"Hi, I reviewed the {opportunity.title} opportunity at {opportunity.company_name}. "
                f"My background in {capability_names} is directly relevant to {problem}. "
                "I would be interested in discussing the specific outcomes you need and whether "
                "a focused engagement is the right fit."
            ),
            grounded_claims=[hyp.statement for hyp in hypotheses if hyp.confidence >= 0.6],
            claims_to_avoid=[
                "Claims about internal company problems not supported by public evidence."
            ],
        )
