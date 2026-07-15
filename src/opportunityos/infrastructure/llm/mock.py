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
from opportunityos.domain.relevance import normalise_text

_SKILL_RULES: dict[str, tuple[str, ...]] = {
    "data science": ("data science", "data scientist"),
    "analytics": ("analytics", "data analysis", "data analyst", "analytical insights"),
    "product analytics": ("product analytics", "product decision intelligence"),
    "retention": ("retention", "churn"),
    "growth": (
        "growth analytics",
        "growth strategy",
        "growth optimisation",
        "growth optimization",
        "user growth",
        "revenue growth",
    ),
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
    "PowerPoint": ("powerpoint", "slide deck", "presentation craftsmanship"),
    "storylining": ("storylining", "storyline", "client deliverable structure"),
    "advisory consulting": (
        "advisory consultant",
        "advisory practice",
        "strategy practice",
        "consulting practice",
    ),
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
    "Growth optimisation": (
        "growth analytics",
        "growth strategy",
        "growth optimisation",
        "growth optimization",
        "user growth",
        "revenue growth",
    ),
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

_RELEVANT_SECTION_RE = re.compile(
    r"\b(?:about this opportunity|about the role|about the position|role overview|job description|"
    r"what you['’]ll do|what you bring|key requirements|requirements|qualifications|nice to have|"
    r"responsibilities|potential business problems|the proposed engagement|the role evaluates)\b",
    re.IGNORECASE,
)
_STOP_SECTION_RE = re.compile(
    r"\b(?:our hiring process|hiring process|our ai expectations|what you['’]ll get|benefits|"
    r"about the client|about the company)\b",
    re.IGNORECASE,
)
_COMPANY_ABOUT_RE = re.compile(
    r"\bAbout\s+(?!This\s+Opportunity\b|the\s+Role\b|the\s+Position\b|the\s+Job\b|"
    r"the\s+Client\b|the\s+Company\b)(?:[A-Z][A-Za-z0-9&.-]*)(?:\s+[A-Z][A-Za-z0-9&.-]*){0,2}\b"
)


def _field(text: str, *names: str) -> str | None:
    alternatives = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?:^|\n)\s*(?:{alternatives})\s*:\s*([^\n]+)", text, re.IGNORECASE)
    return match.group(1).strip(" -*\t") if match else None


def _contains(corpus: str, phrase: str) -> bool:
    normalised_phrase = normalise_text(phrase)
    return f" {normalised_phrase} " in f" {corpus} "


def _matching_labels(corpus: str, rules: dict[str, tuple[str, ...]]) -> list[str]:
    return [label for label, phrases in rules.items() if any(_contains(corpus, phrase) for phrase in phrases)]


def _headline_title(text: str) -> str | None:
    match = re.match(
        r"^\s*(?:(?:expert|job)\s+)?opportunity\s*[-–—:]\s*(.+?)"
        r"(?=\s+about\s+(?:this\s+opportunity|the\s+role)\b|\n|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    title = match.group(1).strip(" -*\t")
    title = re.sub(
        r"\s*\([^)]*(?:\$|hour|week|day|remote|contract)[^)]*\)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()
    return title if 2 <= len(title) <= 180 else None


def _section_markers(text: str) -> list[tuple[int, int, bool]]:
    markers = [
        *((match.start(), match.end(), True) for match in _RELEVANT_SECTION_RE.finditer(text)),
        *((match.start(), match.end(), False) for match in _STOP_SECTION_RE.finditer(text)),
        *((match.start(), match.end(), False) for match in _COMPANY_ABOUT_RE.finditer(text)),
    ]
    markers.sort(key=lambda item: (item[0], item[2], -(item[1] - item[0])))
    deduplicated: list[tuple[int, int, bool]] = []
    for marker in markers:
        if deduplicated and marker[0] < deduplicated[-1][1]:
            continue
        deduplicated.append(marker)
    return deduplicated


def _role_relevant_text(text: str) -> str:
    markers = _section_markers(text)
    if not any(include for _, _, include in markers):
        return text
    chunks: list[str] = []
    for index, (start, _, include) in enumerate(markers):
        if not include:
            continue
        end = markers[index + 1][0] if index + 1 < len(markers) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return "\n".join(chunks) or text


def _type_from_corpus(corpus: str, *, explicit: bool) -> OpportunityType:
    if "fractional" in corpus:
        return OpportunityType.FRACTIONAL
    if "advisory" in corpus or "advisor" in corpus:
        return OpportunityType.ADVISORY
    if "consulting" in corpus or "consultant" in corpus or "independent consulting" in corpus:
        return OpportunityType.CONSULTING
    if "contract" in corpus or "project based" in corpus or "freelance" in corpus:
        return OpportunityType.CONTRACT
    if "full time" in corpus or "permanent role" in corpus or "permanent position" in corpus:
        return OpportunityType.FULL_TIME
    partnership_markers = (
        "partnership opportunity",
        "strategic partnership",
        "equity partnership",
        "partner role",
        "become a partner",
    )
    if explicit and corpus in {"partnership", "partner"}:
        return OpportunityType.PARTNERSHIP
    if any(marker in corpus for marker in partnership_markers):
        return OpportunityType.PARTNERSHIP
    return OpportunityType.UNKNOWN


def _infer_opportunity_type(text: str, explicit_value: str | None, title: str | None) -> OpportunityType:
    if explicit_value:
        explicit_type = _type_from_corpus(normalise_text(explicit_value), explicit=True)
        if explicit_type != OpportunityType.UNKNOWN:
            return explicit_type
    role_corpus = normalise_text(" ".join(filter(None, [title, _role_relevant_text(text)])))
    return _type_from_corpus(role_corpus, explicit=False)


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

        company_value = _field(text, "company", "organisation", "organization", "client")
        company = company_value or source.company_hint or "Unknown company"

        engagement_value = _field(text, "opportunity type", "engagement", "engagement type")
        explicit_title = _field(text, "role", "title", "position")
        headline_title = _headline_title(text)
        title_candidate = explicit_title or headline_title
        opportunity_type = _infer_opportunity_type(text, engagement_value, title_candidate)

        if title_candidate:
            title = title_candidate
        elif engagement_value:
            title = engagement_value
        else:
            title = _fallback_title(company, opportunity_type)

        role_text = "\n".join(
            filter(None, [title_candidate, engagement_value, _role_relevant_text(text)])
        )
        role_corpus = normalise_text(role_text)
        required_skills = _matching_labels(role_corpus, _SKILL_RULES)
        problem_areas = _matching_labels(role_corpus, _PROBLEM_RULES)

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

        seniority = _field(text, "seniority", "level")

        confidence = 0.35 if text else 0.20
        confidence += 0.15 if company_value or source.company_hint else 0.0
        confidence += 0.15 if title_candidate else 0.08 if engagement_value else 0.03
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
