from __future__ import annotations

import re
from copy import deepcopy

from opportunityos.domain.enums import MemoryCategory
from opportunityos.domain.models import Capability, PersonalProfile, WeightedPreference

_SPACE_RE = re.compile(r"\s+")

_PREFERENCE_KEY_ALIASES = {
    "recommendation:similar_profiles": "recommendation:similar_opportunities",
}

_PREFERENCE_LABELS = {
    "recommendation:similar_opportunities": "Opportunities similar to ones I marked worth pursuing",
    "location:flexibility": "Location flexibility",
    "work_style:execution_only": "Execution-only work",
    "seniority:junior": "Junior-level roles",
    "engagement:presented_type": "The engagement type presented in the opportunity",
}

_PROBLEM_AREA_ALIASES = {
    "ai implementation": "AI implementation",
    "artificial intelligence implementation": "AI implementation",
    "ai operational systems": "AI operational systems that produce tangible outputs",
    "ai operational systems that can produce tangible outputs": "AI operational systems that produce tangible outputs",
    "ai operational systems that produce tangible outputs": "AI operational systems that produce tangible outputs",
    "analytics": "Product decision intelligence",
    "product analytics": "Product decision intelligence",
    "data unification": "Customer data unification",
    "customer data unification": "Customer data unification",
    "growth": "Growth optimisation",
    "growth optimization": "Growth optimisation",
    "growth optimisation": "Growth optimisation",
    "retention": "Retention improvement",
    "retention improvement": "Retention improvement",
    "experimentation": "Experimentation systems",
    "experimentation systems": "Experimentation systems",
    "forecasting": "Demand forecasting",
    "demand forecasting": "Demand forecasting",
    "delivery": "Cross-functional delivery",
    "cross functional delivery": "Cross-functional delivery",
    "cross-functional delivery": "Cross-functional delivery",
    "product strategy": "Product strategy",
    "business strategy": "Business strategy",
}

_CAPABILITY_ONLY_PROBLEM_AREAS = {
    "artificial intelligence",
    "data science",
    "growth analytics",
    "product management",
    "project management",
    "python",
    "retention analytics",
    "sql",
}

_ACRONYMS = {
    "ai": "AI",
    "b2b": "B2B",
    "b2c": "B2C",
    "cdp": "CDP",
    "llm": "LLM",
    "ml": "ML",
    "sql": "SQL",
}


def clean_text(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip())


def canonical_identity(value: str) -> str:
    return clean_text(value).casefold()


def canonicalise_preference_key(key: str) -> str:
    cleaned = clean_text(key).casefold()
    if ":" in cleaned:
        namespace, value = cleaned.split(":", 1)
        cleaned = f"{namespace.strip().replace(' ', '_')}:{value.strip().replace(' ', '_')}"
    else:
        cleaned = cleaned.replace(" ", "_")
    return _PREFERENCE_KEY_ALIASES.get(cleaned, cleaned)


def preference_display_label(key: str) -> str:
    canonical = canonicalise_preference_key(key)
    if canonical in _PREFERENCE_LABELS:
        return _PREFERENCE_LABELS[canonical]

    if ":" not in canonical:
        return canonical.replace("_", " ").capitalize()

    namespace, value = canonical.split(":", 1)
    readable = value.replace("_", " ")
    if namespace == "engagement":
        return f"{readable.capitalize()} engagements"
    if namespace == "work_mode":
        return f"{readable.capitalize()} work"
    if namespace == "industry":
        return f"Industry: {readable.title()}"
    if namespace == "location":
        return f"Location: {readable.title()}"
    if namespace == "seniority":
        return f"Seniority: {readable.title()}"
    return f"{namespace.replace('_', ' ').capitalize()}: {readable}"


def _sentence_case(identity: str) -> str:
    words = identity.split()
    rendered = [_ACRONYMS.get(word, word) for word in words]
    for index, word in enumerate(rendered):
        if word not in _ACRONYMS.values():
            rendered[index] = word[:1].upper() + word[1:]
            break
    return " ".join(rendered)


def canonicalise_problem_area(value: str) -> str | None:
    identity = canonical_identity(value)
    if not identity or identity in _CAPABILITY_ONLY_PROBLEM_AREAS:
        return None
    return _PROBLEM_AREA_ALIASES.get(identity, _sentence_case(identity))


def canonicalise_problem_areas(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        canonical = canonicalise_problem_area(value)
        if canonical is None:
            continue
        identity = canonical_identity(canonical)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(canonical)
    return result


def _canonicalise_capabilities(capabilities: list[Capability]) -> list[Capability]:
    result: list[Capability] = []
    by_identity: dict[str, Capability] = {}
    for item in capabilities:
        candidate = item.model_copy(deep=True)
        candidate.name = clean_text(candidate.name)
        identity = canonical_identity(candidate.name)
        existing = by_identity.get(identity)
        if existing is None:
            by_identity[identity] = candidate
            result.append(candidate)
            continue
        existing.proficiency = max(existing.proficiency, candidate.proficiency)
        existing.evidence = list(dict.fromkeys([*existing.evidence, *candidate.evidence]))
    return result


def _canonicalise_preferences(preferences: list[WeightedPreference]) -> list[WeightedPreference]:
    result: list[WeightedPreference] = []
    by_key: dict[str, WeightedPreference] = {}
    for item in preferences:
        candidate = item.model_copy(deep=True)
        candidate.key = canonicalise_preference_key(candidate.key)
        existing = by_key.get(candidate.key)
        if existing is None:
            by_key[candidate.key] = candidate
            result.append(candidate)
            continue

        candidate_rank = (candidate.explicit, candidate.confidence, candidate.last_updated_at)
        existing_rank = (existing.explicit, existing.confidence, existing.last_updated_at)
        if candidate_rank > existing_rank:
            index = result.index(existing)
            result[index] = candidate
            by_key[candidate.key] = candidate
    return result


def canonicalise_profile(profile: PersonalProfile) -> PersonalProfile:
    updated = deepcopy(profile)
    updated.capabilities = _canonicalise_capabilities(updated.capabilities)
    updated.preferences = _canonicalise_preferences(updated.preferences)
    updated.target_problem_areas = canonicalise_problem_areas(updated.target_problem_areas)
    return updated


def memory_display_label(category: MemoryCategory | str, key: str) -> str:
    category_value = category.value if isinstance(category, MemoryCategory) else category
    if category_value == MemoryCategory.PREFERENCE.value:
        return preference_display_label(key)
    return key
