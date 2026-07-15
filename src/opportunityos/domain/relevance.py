from __future__ import annotations

import re
from collections.abc import Iterable

from opportunityos.domain.enums import OpportunityType
from opportunityos.domain.models import OpportunityProfile

_TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

CONCEPT_ALIASES: dict[str, tuple[str, ...]] = {
    "artificial_intelligence": (
        "artificial intelligence",
        "ai implementation",
        "generative ai",
        "gen ai",
        "machine learning",
        "ai",
    ),
    "data_science": ("data science", "data scientist", "predictive modelling", "predictive modeling"),
    "analytics": ("analytics", "data analysis", "data analyst", "analytical insights"),
    "product_analytics": ("product analytics", "product decision intelligence"),
    "retention": ("retention", "churn", "customer lifecycle"),
    "growth": (
        "growth analytics",
        "growth optimisation",
        "growth optimization",
        "growth strategy",
        "user growth",
        "revenue growth",
    ),
    "forecasting": ("demand forecasting", "forecasting", "forecast"),
    "experimentation": ("experimentation systems", "experimentation", "a/b testing", "ab testing"),
    "python": ("python",),
    "sql": ("sql",),
    "excel": ("excel",),
    "power_query": ("power query",),
    "presentation_design": (
        "powerpoint",
        "slide deck",
        "presentation craftsmanship",
        "presentation design",
        "data exhibits",
    ),
    "storylining": ("storylining", "storyline", "client deliverable structure"),
    "advisory_consulting": (
        "advisory consultant",
        "advisory practice",
        "strategy practice",
        "consulting practice",
    ),
    "product_management": ("product management", "product manager", "product strategy"),
    "project_management": ("project management", "project manager", "project delivery"),
    "stakeholder_management": ("stakeholder management", "stakeholder communication"),
    "resource_management": ("resource management", "resource planning"),
    "risk_management": ("risk management", "risk handling", "risk mitigation"),
    "communication": ("communication", "cross-functional communication"),
    "assortment_planning": ("assortment planning", "assortment", "merchandise planning"),
    "inventory_planning": ("inventory planning", "inventory decisions", "inventory optimisation"),
    "replenishment": ("replenishment", "stockout", "stockouts", "excess inventory"),
    "merchandising": ("merchandising", "merchandise"),
    "business_strategy": ("business strategy", "management consulting", "business consulting"),
    "consulting": ("independent consulting", "fractional", "consulting", "consultant", "advisory"),
    "operations": ("operations", "operational systems", "operating model"),
    "gaming": ("gaming", "game", "cricket game", "sports game"),
}

RELATED_CONCEPTS: dict[str, dict[str, float]] = {
    "artificial_intelligence": {"data_science": 0.75, "product_management": 0.35},
    "project_management": {"product_management": 0.65, "stakeholder_management": 0.55},
    "resource_management": {"project_management": 0.75, "product_management": 0.40},
    "risk_management": {"project_management": 0.65, "product_management": 0.35},
    "assortment_planning": {"forecasting": 0.75, "product_analytics": 0.65, "analytics": 0.50},
    "inventory_planning": {"forecasting": 0.80, "product_analytics": 0.60, "analytics": 0.50},
    "replenishment": {"forecasting": 0.75, "product_analytics": 0.50, "analytics": 0.40},
    "merchandising": {"product_analytics": 0.55, "forecasting": 0.45},
    "business_strategy": {"product_management": 0.60, "product_analytics": 0.45},
    "advisory_consulting": {"business_strategy": 0.55, "project_management": 0.30},
    "storylining": {"communication": 0.40, "business_strategy": 0.30},
    "operations": {"project_management": 0.50, "product_management": 0.45},
}

_EXECUTION_ONLY_MARKERS = (
    "data entry",
    "dashboard production",
    "dashboard reporting",
    "excel reporting",
    "manual reporting",
    "power query",
    "report generation",
)

_LOW_OWNERSHIP_MARKERS = (
    "assist with",
    "support the team",
    "prepare reports",
    "report generation",
    "data entry",
    "project coordinator",
    "research assistant",
)

_GENERIC_TITLES = {
    "general opportunity",
    "unspecified opportunity",
    "unknown opportunity",
    *(f"{opportunity_type.value.replace('_', ' ')} opportunity" for opportunity_type in OpportunityType),
}
_GENERIC_TITLE_PREFIXES = ("opportunity at ",)


def normalise_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold()))


def stem(token: str) -> str:
    for suffix in ("ments", "ment", "ing", "ers", "er", "ies", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            if suffix == "ies":
                return token[:-3] + "y"
            return token[: -len(suffix)]
    return token


def meaningful_tokens(values: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(
            stem(token)
            for token in _TOKEN_RE.findall(value.casefold())
            if token not in _STOPWORDS and len(token) > 1
        )
    return result


def extract_concepts(values: Iterable[str]) -> set[str]:
    corpus = f" {normalise_text(' '.join(values))} "
    concepts: set[str] = set()
    for concept, aliases in CONCEPT_ALIASES.items():
        if any(f" {normalise_text(alias)} " in corpus for alias in aliases):
            concepts.add(concept)
    if "product_analytics" in concepts:
        concepts.discard("analytics")
    return concepts


def infer_seniority(value: str | None) -> str | None:
    text = normalise_text(value or "")
    if not text:
        return None
    patterns = (
        ("intern", ("intern", "internship")),
        ("junior", ("junior", "jr")),
        ("associate", ("associate",)),
        ("executive", ("chief", "cxo", "vp", "vice president")),
        ("director", ("director", "head of")),
        ("lead", ("principal", "lead")),
        ("senior", ("senior", "sr")),
        ("manager", ("manager", "management")),
    )
    padded = f" {text} "
    for label, markers in patterns:
        if any(f" {marker} " in padded for marker in markers):
            return label
    unqualified_junior_titles = (
        "data analyst",
        "business analyst",
        "reporting analyst",
        "project coordinator",
        "research assistant",
    )
    if any(marker in text for marker in unqualified_junior_titles):
        return "junior"
    return None


def infer_work_mode(opportunity: OpportunityProfile) -> str | None:
    location = normalise_text(opportunity.location or "")
    if "hybrid" in location:
        return "hybrid"
    if opportunity.remote_allowed is True or "remote" in location:
        return "remote"
    if opportunity.remote_allowed is False or "onsite" in location or "on site" in location:
        return "onsite"
    return None


def engagement_facets(opportunity_type: OpportunityType) -> set[str]:
    mapping = {
        OpportunityType.CONSULTING: {"consulting"},
        OpportunityType.FRACTIONAL: {"fractional", "consulting"},
        OpportunityType.CONTRACT: {"contract"},
        OpportunityType.FULL_TIME: {"full_time", "full time"},
        OpportunityType.ADVISORY: {"advisory", "consulting"},
        OpportunityType.PARTNERSHIP: {"partnership"},
        OpportunityType.UNKNOWN: set(),
    }
    return mapping[opportunity_type]


def is_execution_only(opportunity: OpportunityProfile) -> bool:
    corpus = normalise_text(
        " ".join([opportunity.title, *opportunity.required_skills, *opportunity.responsibilities])
    )
    return any(marker in corpus for marker in _EXECUTION_ONLY_MARKERS)


def is_low_ownership(opportunity: OpportunityProfile) -> bool:
    corpus = normalise_text(
        " ".join([opportunity.title, *opportunity.problem_areas, *opportunity.responsibilities])
    )
    return is_execution_only(opportunity) or any(marker in corpus for marker in _LOW_OWNERSHIP_MARKERS)


def has_generic_opportunity_title(opportunity: OpportunityProfile) -> bool:
    title = normalise_text(opportunity.title)
    return title in _GENERIC_TITLES or any(title.startswith(prefix) for prefix in _GENERIC_TITLE_PREFIXES)
