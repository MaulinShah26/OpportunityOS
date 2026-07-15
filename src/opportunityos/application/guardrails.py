from __future__ import annotations

import re
from collections.abc import Iterable

from opportunityos.domain.enums import CriticSeverity, Decision, EvidenceType
from opportunityos.domain.models import (
    BusinessHypothesis,
    CriticResult,
    GuardrailIssue,
    OpportunityProfile,
    OutreachDraft,
    Recommendation,
)

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


def evaluate_guardrails(
    opportunity: OpportunityProfile,
    hypotheses: list[BusinessHypothesis],
    recommendation: Recommendation,
    outreach: OutreachDraft | None,
    *,
    initial_issues: Iterable[GuardrailIssue] = (),
) -> CriticResult:
    """Validate evidence lineage and block outreach that contains unsupported claims."""
    issues: list[GuardrailIssue] = list(initial_issues)
    evidence_by_id = {item.id: item for item in opportunity.evidence}
    supported_statements: set[str] = {
        _normalise(item.claim) for item in opportunity.evidence
    }

    for hypothesis in hypotheses:
        missing_ids = [item_id for item_id in hypothesis.evidence_ids if item_id not in evidence_by_id]
        if missing_ids:
            issues.append(
                GuardrailIssue(
                    code="unknown_evidence_reference",
                    message="The hypothesis references evidence that is not present in the opportunity.",
                    severity=CriticSeverity.BLOCKING,
                    claim=hypothesis.statement,
                )
            )
            continue

        requires_evidence = hypothesis.claim_type in {
            EvidenceType.OBSERVED_FACT,
            EvidenceType.SUPPORTED_INFERENCE,
        }
        if requires_evidence and not hypothesis.evidence_ids:
            issues.append(
                GuardrailIssue(
                    code="missing_evidence",
                    message="A factual or supported claim has no evidence lineage.",
                    severity=CriticSeverity.BLOCKING,
                    claim=hypothesis.statement,
                )
            )
            continue

        linked_evidence = [evidence_by_id[item_id] for item_id in hypothesis.evidence_ids]
        if requires_evidence and linked_evidence:
            if not _claim_matches_evidence(
                hypothesis.statement,
                linked_evidence,
                opportunity.company_name,
            ):
                issues.append(
                    GuardrailIssue(
                        code="evidence_claim_mismatch",
                        message="The cited evidence does not materially support the hypothesis wording.",
                        severity=CriticSeverity.BLOCKING,
                        claim=hypothesis.statement,
                    )
                )
                continue
            max_evidence_confidence = max(item.confidence for item in linked_evidence)
            if hypothesis.confidence > max_evidence_confidence + 0.15:
                issues.append(
                    GuardrailIssue(
                        code="overstated_confidence",
                        message="Claim confidence materially exceeds its strongest supporting evidence.",
                        severity=CriticSeverity.WARNING,
                        claim=hypothesis.statement,
                    )
                )

        if hypothesis.claim_type == EvidenceType.SPECULATIVE_HYPOTHESIS:
            if hypothesis.confidence > 0.6:
                issues.append(
                    GuardrailIssue(
                        code="high_confidence_speculation",
                        message="A speculative hypothesis is expressed with excessive confidence.",
                        severity=CriticSeverity.WARNING,
                        claim=hypothesis.statement,
                    )
                )
            continue

        supported_statements.add(_normalise(hypothesis.statement))

    if recommendation.decision == Decision.PURSUE and not opportunity.evidence:
        issues.append(
            GuardrailIssue(
                code="pursue_without_evidence",
                message="A pursue recommendation requires at least one evidence claim.",
                severity=CriticSeverity.WARNING,
            )
        )

    unsupported_claims: list[str] = []
    if outreach is not None:
        for claim in outreach.grounded_claims:
            if _normalise(claim) not in supported_statements:
                unsupported_claims.append(claim)
        unsupported_claims.extend(
            _unsupported_company_sentences(
                outreach.body,
                opportunity.company_name,
                supported_statements,
            )
        )
        unsupported_claims = list(dict.fromkeys(unsupported_claims))
        if unsupported_claims:
            issues.append(
                GuardrailIssue(
                    code="unsupported_outreach_claim",
                    message="The outreach draft contains claims without valid evidence lineage.",
                    severity=CriticSeverity.BLOCKING,
                    claim="; ".join(unsupported_claims),
                )
            )

    blocking = any(issue.severity == CriticSeverity.BLOCKING for issue in issues)
    return CriticResult(
        passed=not blocking,
        block_outreach=blocking and outreach is not None,
        issues=issues,
        unsupported_claims=unsupported_claims,
        blocked_draft=outreach if blocking and outreach is not None else None,
    )


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str) -> set[str]:
    result: set[str] = set()
    for token in _TOKEN_RE.findall(value.casefold()):
        if token in _STOPWORDS or len(token) <= 1:
            continue
        for suffix in ("ments", "ment", "ing", "ers", "er", "ies", "es", "s"):
            if len(token) > len(suffix) + 3 and token.endswith(suffix):
                token = token[:-3] + "y" if suffix == "ies" else token[: -len(suffix)]
                break
        result.add(token)
    return result


def _claim_matches_evidence(
    statement: str,
    linked_evidence: list[object],
    company_name: str,
) -> bool:
    company_tokens = _tokens(company_name)
    claim_tokens = _tokens(statement) - company_tokens
    if not claim_tokens:
        return False
    evidence_text = " ".join(
        f"{getattr(item, 'claim', '')} {getattr(item, 'supporting_excerpt', '')}"
        for item in linked_evidence
    )
    overlap = claim_tokens & (_tokens(evidence_text) - company_tokens)
    required = 1 if len(claim_tokens) <= 3 else max(2, round(len(claim_tokens) * 0.3))
    return len(overlap) >= required


def _unsupported_company_sentences(
    body: str,
    company_name: str,
    supported_statements: set[str],
) -> list[str]:
    risky_phrases = (
        "is facing",
        "are facing",
        "has a problem",
        "have a problem",
        "needs urgent",
        "must fix",
        "is struggling",
        "are struggling",
        "is falling",
        "are falling",
        "is declining",
        "are declining",
        "lacks ",
        "suffers ",
    )
    sentences = [item.strip() for item in body.replace("!", ".").replace("?", ".").split(".")]
    unsupported: list[str] = []
    company_tokens = {company_name.casefold(), "your", "you"}
    for sentence in sentences:
        normalised = _normalise(sentence)
        if not normalised:
            continue
        mentions_company = any(token in normalised for token in company_tokens)
        risky = any(phrase in normalised for phrase in risky_phrases)
        supported = any(statement in normalised or normalised in statement for statement in supported_statements)
        if mentions_company and risky and not supported:
            unsupported.append(sentence)
    return unsupported
