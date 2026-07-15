from __future__ import annotations

import re
from collections.abc import Iterable

from opportunityos.domain.enums import ConstraintKind, Decision
from opportunityos.domain.models import (
    FitScore,
    OpportunityProfile,
    PersonalProfile,
    Recommendation,
    ScoreDimension,
)

TOKEN_RE = re.compile(r"[a-z0-9+#.]+")
DEFAULT_HOLD_THRESHOLD = 45
DEFAULT_PURSUE_THRESHOLD = 72
DEFAULT_MIN_EXTRACTION_CONFIDENCE = 0.60


def _tokens(values: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(TOKEN_RE.findall(value.lower()))
    return result


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _preference_score(profile: PersonalProfile, opportunity: OpportunityProfile) -> tuple[float, str]:
    relevant = []
    opportunity_values = {
        opportunity.opportunity_type.value,
        (opportunity.location or "").lower(),
        "remote" if opportunity.remote_allowed else "onsite",
    }
    for preference in profile.preferences:
        key = preference.key.lower()
        if any(key in value or value in key for value in opportunity_values if value):
            relevant.append(preference.weight * preference.confidence)
    if not relevant:
        return 0.5, "No directly matching explicit preference; neutral score applied."
    score = sum(relevant) / len(relevant)
    return score, "Matched weighted engagement, location, or work-style preferences."


def _constraint_score(profile: PersonalProfile, opportunity: OpportunityProfile) -> tuple[float, list[str], str]:
    candidate_values = {
        opportunity.opportunity_type.value.lower(),
        (opportunity.location or "").lower(),
        "remote" if opportunity.remote_allowed else "onsite",
        (opportunity.seniority or "").lower(),
    }
    hard_breaches: list[str] = []
    penalties = 0.0
    for constraint in profile.constraints:
        rejected = {value.lower() for value in constraint.rejected_values}
        matched_rejections = rejected & candidate_values
        if matched_rejections:
            if constraint.kind == ConstraintKind.HARD:
                hard_breaches.append(f"{constraint.key}: {', '.join(sorted(matched_rejections))}")
            else:
                penalties += constraint.penalty
    if hard_breaches:
        return 0.0, hard_breaches, "One or more hard constraints were violated."
    return max(0.0, 1.0 - min(1.0, penalties)), [], "No hard constraint violations detected."


def calculate_fit(profile: PersonalProfile, opportunity: OpportunityProfile) -> FitScore:
    capability_terms = _tokens(cap.name for cap in profile.capabilities)
    opportunity_terms = _tokens(
        [*opportunity.required_skills, *opportunity.problem_areas, *opportunity.responsibilities]
    )
    capability_score = min(1.0, _jaccard(capability_terms, opportunity_terms) * 2.5)

    preference_score, preference_explanation = _preference_score(profile, opportunity)
    constraint_score, hard_breaches, constraint_explanation = _constraint_score(profile, opportunity)

    aspiration_terms = _tokens(item.name for item in profile.aspirations)
    aspiration_score = min(1.0, _jaccard(aspiration_terms, opportunity_terms) * 2.5)
    if not aspiration_terms:
        aspiration_score = 0.5

    evidence_score = min(
        1.0,
        (len(opportunity.evidence) / 4.0) * max(opportunity.extraction_confidence, 0.25),
    )

    dimensions = [
        ScoreDimension(
            name="capability_fit",
            score=capability_score,
            weight=0.30,
            explanation="Overlap between evidenced capabilities and opportunity requirements.",
        ),
        ScoreDimension(
            name="preference_fit",
            score=preference_score,
            weight=0.20,
            explanation=preference_explanation,
        ),
        ScoreDimension(
            name="constraint_compatibility",
            score=constraint_score,
            weight=0.25,
            explanation=constraint_explanation,
        ),
        ScoreDimension(
            name="future_direction_fit",
            score=aspiration_score,
            weight=0.15,
            explanation="Overlap with the user's stated future direction.",
        ),
        ScoreDimension(
            name="evidence_quality",
            score=evidence_score,
            weight=0.10,
            explanation="Coverage and confidence of source-backed evidence.",
        ),
    ]
    weighted = sum(d.score * d.weight for d in dimensions)
    total = 0 if hard_breaches else round(weighted * 100)
    return FitScore(total=total, dimensions=dimensions, hard_constraint_breaches=hard_breaches)


def decision_for_thresholds(
    *,
    fit_total: int,
    extraction_confidence: float,
    has_hard_constraint_breach: bool,
    hold_threshold: int = DEFAULT_HOLD_THRESHOLD,
    pursue_threshold: int = DEFAULT_PURSUE_THRESHOLD,
    min_extraction_confidence: float = DEFAULT_MIN_EXTRACTION_CONFIDENCE,
) -> Decision:
    """Apply a transparent decision policy without constructing recommendation copy."""
    if has_hard_constraint_breach:
        return Decision.REJECT
    if fit_total >= pursue_threshold and extraction_confidence >= min_extraction_confidence:
        return Decision.PURSUE
    if fit_total >= hold_threshold:
        return Decision.HOLD
    return Decision.REJECT


def recommend(fit: FitScore, opportunity: OpportunityProfile) -> Recommendation:
    decision = decision_for_thresholds(
        fit_total=fit.total,
        extraction_confidence=opportunity.extraction_confidence,
        has_hard_constraint_breach=bool(fit.hard_constraint_breaches),
    )
    if fit.hard_constraint_breaches:
        return Recommendation(
            decision=Decision.REJECT,
            rationale="The opportunity violates a user-defined hard constraint.",
            risks=fit.hard_constraint_breaches,
            next_action="Do not pursue unless the user explicitly changes the relevant constraint.",
        )
    if decision == Decision.PURSUE:
        return Recommendation(
            decision=Decision.PURSUE,
            rationale="The opportunity has strong personal relevance and sufficient evidence.",
            risks=[],
            next_action="Review the evidence and personalise the draft before contacting anyone.",
        )
    if decision == Decision.HOLD:
        return Recommendation(
            decision=Decision.HOLD,
            rationale="The opportunity is plausible, but the fit or evidence is not yet strong enough.",
            risks=["Additional evidence or clarification is required."],
            next_action="Collect missing role, engagement, location, or company information.",
        )
    return Recommendation(
        decision=Decision.REJECT,
        rationale="The opportunity is materially weaker than the user's current priorities.",
        risks=["Low relevance relative to alternative opportunities."],
        next_action="Archive it and preserve the rejection reason as a learning signal.",
    )
