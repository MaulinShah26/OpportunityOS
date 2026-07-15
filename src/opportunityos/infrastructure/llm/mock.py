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
from opportunityos.domain.relevance import infer_seniority, normalise_text

_SKILL_RULES: dict[str, tuple[str, ...]] = {
    "data science": ("data science", "data scientist"),
    "analytics": ("analytics", "data analysis", "data analyst"),
    "product analytics": ("product analytics", "product decision intelligence"),
    "retention": ("retention", "churn"),
    "growth": ("growth",),
    "ai": ("artificial intelligence", "generative ai", "gen ai", " ai "),
    "AI implementation": ("ai implementation", "implementing ai", "practical ai systems"),
    "machine learning": ("machine learning",),
    "forecasting": ("forecasting", "forecast"),
    "demand forecasting": ("demand forecasting", "demand planning"),
    "experimentation": ("experimentation", "a/b testing", "ab testing"),
    "Python": ("python",),
    "SQL": ("sql",),
    "Excel": ("excel",),
    "Power Query": ("power query",),
    "product management": ("product management", "product manager", "product strategy"),
    "project management": ("project management", "project manager", "project delivery"),
    "stakeholder management": ("stakeholder management",),
    "resource management": ("resource management", "resource planning"),
    "risk management": ("risk management", "risk handling", "risk mitigation"),
    "communication": ("communication",),
    "assortment planning": ("assortment planning", "store-level assortment", "assortment"),
    "inventory planning": ("inventory planning", "inventory decisions", "excess inventory"),
    "replenishment": ("replenishment", "stockout", "stockouts"),
    "merchandising": ("merchandising", "merchandise planning"),
}

_PROBLEM_RULES: dict[str, tuple[str, ...]] = {
    "Retention improvement": ("retention", "churn"),
    "Growth optimisation": ("growth",),
    "Demand forecasting": ("demand forecasting", "demand planning", "forecasting"),
    "Experimentation systems": ("experimentation", "a/b testing", "ab testing"),
    "AI implementation": ("ai implementation", "implementing ai", "practical ai systems"),
    "Assortment planning": ("assortment planning", "store-level assortment", "assortment"),
    "Inventory and replenishment": (
        "inventory planning",
        "inventory decisions",
        "replenishment",
        "stockout",
        "excess inventory",
    ),
    "Project delivery": ("project management", "planning, execution and delivery", "project delivery"),
    "Risk management": ("risk management", "risk handling", "risk mitigation"),
    "Product strategy": ("product strategy", "product management"),
}


def _field(text: str, *names: str) -> str | None:
    alternatives = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?:^|\n)\s*(?:{alternatives})\s*:\s*([^\n]+)", text, re.IGNORECASE)
    return match.group(1).strip(" -*\t") if match else None


def _contains(corpus: str, phrase: str) -> bool:
    normalised_phrase = normalise_text(phrase)
    return f" {normalised_phrase} " in f" {corpus} "


def _matching_labels(corpus: str, rules: dict[str, tuple[str, ...]]) -> list[str]:
    return [label for label, phrases in rules.items() if any(_contains(corpus, phrase) for phrase in phrases)]


def _infer_opportunity_type(text: str, explicit_value: str | None) -> OpportunityType:
    corpus = normalise_text(" ".join(filter(None, [explicit_value, text])))
    if "fractional" in corpus:
        return OpportunityType.FRACTIONAL
    if "advisory" in corpus or "advisor" in corpus:
        return OpportunityType.ADVISORY
    if "consulting" in corpus or "consultant" in corpus or "independent consulting" in corpus:
        return OpportunityType.CONSULTING
    if "contract" in corpus or "project based" in corpus:
        return OpportunityType.CONTRACT
    if "full time" in corpus or "permanent role" in corpus:
        return OpportunityType.FULL_TIME
    if "partnership" in corpus or "partner opportunity" in corpus:
        return OpportunityType.PARTNERSHIP
    return OpportunityType.UNKNOWN


def _fallback_title(company: str, opportunity_type: OpportunityType) -> str:
    if opportunity_type != OpportunityType.UNKNOWN:
        label = opportunity_type.value.replace("_", " ").title()
        return f"{label} opportunity"
    if company != "Unknown company":
        return f"Opportunity at {company}"
    return "General opportunity"


class MockOpportunityExtractor:
    def extract(self, source: OpportunityInput, evidence: list[EvidenceClaim]) -> OpportunityProfile:
        text = (source.raw_text or "").strip()
        corpus = normalise_text(text)

        company_value = _field(text, "company", "organisation", "organization", "client")
        company = company_value or source.company_hint or "Unknown company"

        engagement_value = _field(text, "opportunity type", "engagement", "engagement type")
        opportunity_type = _infer_opportunity_type(text, engagement_value)

        explicit_title = _field(text, "role", "title", "position")
        if explicit_title:
            title = explicit_title
        elif engagement_value:
            title = engagement_value
        else:
            title = _fallback_title(company, opportunity_type)

        required_skills = _matching_labels(corpus, _SKILL_RULES)
        problem_areas = _matching_labels(corpus, _PROBLEM_RULES)

        location = _field(text, "location")
        work_mode = _field(text, "work mode", "working model")
        mode_corpus = normalise_text(" ".join(filter(None, [work_mode, location, text])))
        if "hybrid" in mode_corpus:
            remote = True
            location = location or "Hybrid"
        elif "remote" in mode_corpus:
            remote = True
            location = location or "Remote"
        elif "onsite" in mode_corpus or "on site" in mode_corpus:
            remote = False
            location = location or "Onsite"
        else:
            remote = None

        explicit_seniority = _field(text, "seniority", "level")
        seniority = explicit_seniority or infer_seniority(title)

        confidence = 0.35 if text else 0.20
        confidence += 0.15 if company_value or source.company_hint else 0.0
        confidence += 0.15 if explicit_title else 0.08 if engagement_value else 0.03
        confidence += 0.10 if opportunity_type != OpportunityType.UNKNOWN else 0.0
        confidence += 0.10 if required_skills or problem_areas else 0.0
        confidence += 0.05 if location or work_mode else 0.0
        confidence = min(0.92, confidence)

        responsibilities = list(dict.fromkeys([*problem_areas, *required_skills]))
        return OpportunityProfile(
            company_name=company,
            title=title,
            opportunity_type=opportunity_type,
            location=location,
            remote_allowed=remote,
            seniority=seniority,
            required_skills=required_skills,
            responsibilities=responsibilities,
            problem_areas=problem_areas,
            evidence=evidence,
            extraction_confidence=confidence,
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
