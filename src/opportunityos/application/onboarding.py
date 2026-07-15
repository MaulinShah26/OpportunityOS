from __future__ import annotations

import re
from dataclasses import dataclass

from opportunityos.domain.models import Capability, PersonalProfile, ResumeOnboardingRequest
from opportunityos.domain.taxonomy import canonicalise_problem_areas


@dataclass(frozen=True)
class CapabilityRule:
    name: str
    keywords: tuple[str, ...]
    problem_areas: tuple[str, ...] = ()


CAPABILITY_RULES = (
    CapabilityRule(
        "product analytics",
        ("product analytics", "product analyst", "product metrics"),
        ("product decision intelligence",),
    ),
    CapabilityRule(
        "data science",
        ("data scientist", "data science", "predictive model", "machine learning"),
    ),
    CapabilityRule(
        "artificial intelligence",
        ("artificial intelligence", "generative ai", "agentic ai", " llm", "ai innovation"),
        ("AI implementation",),
    ),
    CapabilityRule(
        "retention analytics",
        ("retention", "cohort", "churn"),
        ("retention improvement",),
    ),
    CapabilityRule(
        "growth analytics",
        ("growth", "conversion", "activation", "funnel"),
        ("growth optimisation",),
    ),
    CapabilityRule(
        "experimentation",
        ("a/b test", "ab test", "experimentation", "hypothesis testing"),
        ("experimentation systems",),
    ),
    CapabilityRule(
        "forecasting",
        ("forecast", "time series", "demand planning"),
        ("demand forecasting",),
    ),
    CapabilityRule(
        "customer data",
        ("customer data platform", "cdp", "identity resolution", "customer 360"),
        ("customer data unification",),
    ),
    CapabilityRule(
        "product management",
        ("product manager", "product management", "product roadmap", "prd"),
        ("product strategy",),
    ),
    CapabilityRule(
        "project management",
        ("project management", "program management", "delivery management", "stakeholder management"),
        ("cross-functional delivery",),
    ),
    CapabilityRule("python", ("python", "pandas", "scikit-learn")),
    CapabilityRule("sql", (" sql", "bigquery", "snowflake", "postgresql")),
    CapabilityRule(
        "business consulting",
        ("consulting", "business strategy", "management consulting"),
        ("business strategy",),
    ),
)


def _normalise(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower()).strip()


def _evidence_excerpt(text: str, keywords: tuple[str, ...]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(keyword.strip() in lowered for keyword in keywords):
            return line[:500]
    return text.strip()[:500]


def build_profile_from_resume(
    request: ResumeOnboardingRequest,
) -> tuple[PersonalProfile, list[str], list[str]]:
    normalised = _normalise(request.resume_text)
    capabilities: list[Capability] = []
    inferred_problem_areas: list[str] = []

    for rule in CAPABILITY_RULES:
        matched = [keyword for keyword in rule.keywords if keyword in normalised]
        if not matched:
            continue
        proficiency = min(0.9, 0.58 + 0.08 * len(matched))
        capabilities.append(
            Capability(
                name=rule.name,
                proficiency=proficiency,
                evidence=[_evidence_excerpt(request.resume_text, rule.keywords)],
            )
        )
        inferred_problem_areas.extend(rule.problem_areas)

    if not capabilities:
        capabilities.append(
            Capability(
                name="general professional experience",
                proficiency=0.5,
                evidence=[request.resume_text.strip()[:500]],
            )
        )

    problem_areas = canonicalise_problem_areas([*request.target_problem_areas, *inferred_problem_areas])
    headline = request.headline or _infer_headline(request.resume_text)
    profile = PersonalProfile(
        display_name=request.display_name,
        headline=headline,
        capabilities=capabilities,
        preferences=request.preferences,
        constraints=request.constraints,
        aspirations=request.aspirations,
        target_problem_areas=problem_areas,
    )
    return profile, [item.name for item in capabilities], problem_areas


def _infer_headline(resume_text: str) -> str:
    for line in resume_text.splitlines():
        candidate = line.strip()
        if 5 <= len(candidate) <= 120 and not re.search(r"@|\+?\d{8,}", candidate):
            return candidate
    return "Professional opportunity profile"
