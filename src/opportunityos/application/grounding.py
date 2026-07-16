from __future__ import annotations

import re
from collections.abc import Iterable

from opportunityos.domain.enums import CriticSeverity
from opportunityos.domain.models import EvidenceClaim, GuardrailIssue, OpportunityInput, OpportunityProfile

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
_GROUNDING_ALIASES: dict[str, tuple[str, ...]] = {
    "analytics": ("data analyst", "data analysis", "analytical insights", "analytical"),
    "ai": ("artificial intelligence", "ai driven", "ai tools", "language model"),
    "powerpoint": ("powerpoint", "slide deck", "presentations"),
    "storylining": ("storylining", "storyline", "client deliverable structure"),
    "advisory consulting": (
        "advisory consultant",
        "advisory practice",
        "strategy practice",
        "consulting practice",
    ),
}


def _stem(token: str) -> str:
    for suffix in ("ments", "ment", "ing", "ers", "er", "ies", "es", "s"):
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            if suffix == "ies":
                return token[:-3] + "y"
            return token[: -len(suffix)]
    return token


def _tokens(value: str) -> set[str]:
    return {
        _stem(token)
        for token in _TOKEN_RE.findall(value.casefold())
        if token not in _STOPWORDS and len(token) > 1
    }


def _normalise(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold()))


def _corpus(source: OpportunityInput, evidence: Iterable[EvidenceClaim]) -> str:
    parts = [
        source.raw_text or "",
        source.company_hint or "",
        source.role_hint or "",
        str(source.source_url or ""),
    ]
    for item in evidence:
        parts.extend([item.claim, item.supporting_excerpt, str(item.source_url or "")])
    return "\n".join(parts)


def _supported(value: str | None, corpus_tokens: set[str], corpus_text: str) -> bool:
    if not value:
        return True
    normalised_value = _normalise(value)
    aliases = _GROUNDING_ALIASES.get(normalised_value, ())
    if any(f" {alias_text} " in f" {corpus_text} " for alias_text in map(_normalise, aliases)):
        return True
    value_tokens = _tokens(value)
    if not value_tokens:
        return True
    overlap = value_tokens & corpus_tokens
    required = 1 if len(value_tokens) <= 2 else max(2, round(len(value_tokens) * 0.45))
    return len(overlap) >= required


def _filter_values(
    values: list[str],
    *,
    corpus_tokens: set[str],
    corpus_text: str,
    field_name: str,
    issues: list[GuardrailIssue],
) -> list[str]:
    grounded: list[str] = []
    for value in values:
        if _supported(value, corpus_tokens, corpus_text):
            grounded.append(value)
            continue
        issues.append(
            GuardrailIssue(
                code="unsupported_extracted_value",
                message=f"Removed an extracted {field_name} value that was not supported by the supplied source.",
                severity=CriticSeverity.WARNING,
                claim=value,
            )
        )
    return grounded


def ground_extracted_opportunity(
    source: OpportunityInput,
    evidence: list[EvidenceClaim],
    opportunity: OpportunityProfile,
) -> tuple[OpportunityProfile, list[GuardrailIssue]]:
    """Remove unsupported extracted facts before they can influence scoring or outreach."""
    grounded = opportunity.model_copy(deep=True)
    grounded.evidence = list(evidence)
    issues: list[GuardrailIssue] = []
    raw_corpus = _corpus(source, evidence)
    corpus_tokens = _tokens(raw_corpus)
    corpus_text = _normalise(raw_corpus)
    removed = 0
    considered = 0

    if source.company_hint:
        grounded.company_name = source.company_hint.strip()
    elif not _supported(grounded.company_name, corpus_tokens, corpus_text):
        issues.append(
            GuardrailIssue(
                code="unsupported_company_name",
                message="The extracted company name was not present in the supplied source.",
                severity=CriticSeverity.WARNING,
                claim=grounded.company_name,
            )
        )
        grounded.company_name = "Unknown company"
        removed += 1
    considered += 1

    if source.role_hint:
        grounded.title = source.role_hint.strip()
    elif not _supported(grounded.title, corpus_tokens, corpus_text):
        issues.append(
            GuardrailIssue(
                code="unsupported_opportunity_title",
                message="The extracted opportunity title was not supported by the supplied source.",
                severity=CriticSeverity.WARNING,
                claim=grounded.title,
            )
        )
        grounded.title = "General opportunity"
        removed += 1
    considered += 1

    scalar_fields = ("location", "seniority", "compensation_text")
    for field_name in scalar_fields:
        value = getattr(grounded, field_name)
        if value is None:
            continue
        considered += 1
        if _supported(value, corpus_tokens, corpus_text):
            continue
        setattr(grounded, field_name, None)
        removed += 1
        issues.append(
            GuardrailIssue(
                code="unsupported_extracted_field",
                message=f"Removed an extracted {field_name.replace('_', ' ')} that was not supported by the source.",
                severity=CriticSeverity.WARNING,
                claim=value,
            )
        )

    for field_name in ("required_skills", "responsibilities", "problem_areas"):
        values = list(getattr(grounded, field_name))
        considered += len(values)
        filtered = _filter_values(
            values,
            corpus_tokens=corpus_tokens,
            corpus_text=corpus_text,
            field_name=field_name.replace("_", " "),
            issues=issues,
        )
        removed += len(values) - len(filtered)
        setattr(grounded, field_name, filtered)

    if considered:
        retention = max(0.35, 1.0 - (removed / considered))
        grounded.extraction_confidence = min(grounded.extraction_confidence, retention)

    return grounded, issues
