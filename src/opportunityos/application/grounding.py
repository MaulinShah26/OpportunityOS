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


def _corpus(source: OpportunityInput, evidence: Iterable[EvidenceClaim]) -> str:
    parts = [source.raw_text or "", source.company_hint or "", str(source.source_url or "")]
    for item in evidence:
        parts.extend([item.claim, item.supporting_excerpt, str(item.source_url or "")])
    return "\n".join(parts)


def _supported(value: str | None, corpus_tokens: set[str]) -> bool:
    if not value:
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
    field_name: str,
    issues: list[GuardrailIssue],
) -> list[str]:
    grounded: list[str] = []
    for value in values:
        if _supported(value, corpus_tokens):
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
    corpus_tokens = _tokens(_corpus(source, evidence))
    removed = 0
    considered = 0

    if source.company_hint:
        grounded.company_name = source.company_hint.strip()
    elif not _supported(grounded.company_name, corpus_tokens):
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

    scalar_fields = ("location", "seniority", "compensation_text")
    for field_name in scalar_fields:
        value = getattr(grounded, field_name)
        if value is None:
            continue
        considered += 1
        if _supported(value, corpus_tokens):
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
            field_name=field_name.replace("_", " "),
            issues=issues,
        )
        removed += len(values) - len(filtered)
        setattr(grounded, field_name, filtered)

    if considered:
        retention = max(0.35, 1.0 - (removed / considered))
        grounded.extraction_confidence = min(grounded.extraction_confidence, retention)

    return grounded, issues
