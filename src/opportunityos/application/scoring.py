from __future__ import annotations

from collections.abc import Iterable

from opportunityos.domain.enums import ConstraintKind, Decision
from opportunityos.domain.models import (
    FitScore,
    OpportunityProfile,
    PersonalProfile,
    Recommendation,
    ScoreDimension,
    WeightedPreference,
)
from opportunityos.domain.relevance import (
    RELATED_CONCEPTS,
    engagement_facets,
    extract_concepts,
    infer_seniority,
    infer_work_mode,
    is_execution_only,
    meaningful_tokens,
    normalise_text,
)

DEFAULT_HOLD_THRESHOLD = 45
DEFAULT_PURSUE_THRESHOLD = 72
DEFAULT_MIN_EXTRACTION_CONFIDENCE = 0.60


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _profile_concept_strengths(profile: PersonalProfile) -> dict[str, float]:
    strengths: dict[str, float] = {}
    for capability in profile.capabilities:
        for concept in extract_concepts([capability.name]):
            strengths[concept] = max(strengths.get(concept, 0.0), capability.proficiency)
    return strengths


def _opportunity_values(opportunity: OpportunityProfile) -> list[str]:
    return [
        opportunity.title,
        opportunity.opportunity_type.value,
        *opportunity.required_skills,
        *opportunity.problem_areas,
        *opportunity.responsibilities,
    ]


def _concept_strength(concept: str, profile_strengths: dict[str, float]) -> float:
    direct = profile_strengths.get(concept, 0.0)
    related = max(
        (
            profile_strengths.get(profile_concept, 0.0) * factor
            for profile_concept, factor in RELATED_CONCEPTS.get(concept, {}).items()
        ),
        default=0.0,
    )
    return max(direct, related)


def _capability_score(profile: PersonalProfile, opportunity: OpportunityProfile) -> tuple[float, str]:
    opportunity_concepts = extract_concepts(_opportunity_values(opportunity))
    if opportunity_concepts:
        profile_strengths = _profile_concept_strengths(profile)
        matched = {
            concept: _concept_strength(concept, profile_strengths) for concept in opportunity_concepts
        }
        score = sum(matched.values()) / len(matched)
        covered = sum(value > 0 for value in matched.values())
        return score, f"Covered {covered} of {len(matched)} recognised capability areas."

    profile_tokens = meaningful_tokens(capability.name for capability in profile.capabilities)
    opportunity_tokens = meaningful_tokens(_opportunity_values(opportunity))
    if not opportunity_tokens:
        return 0.25, "The source did not expose enough role content for a strong capability comparison."
    overlap = len(profile_tokens & opportunity_tokens) / len(opportunity_tokens)
    return min(0.65, overlap), "Used direct term coverage because no recognised capability areas were found."


def _directional_preference_value(preference: WeightedPreference) -> float:
    multiplier = 6.0 if preference.explicit else 2.5
    return _clamp(0.5 + ((preference.weight - 0.5) * multiplier * preference.confidence))


def _preference_facets(opportunity: OpportunityProfile) -> dict[str, set[str]]:
    work_mode = infer_work_mode(opportunity)
    seniority = opportunity.seniority or infer_seniority(opportunity.title)
    return {
        "engagement": {normalise_text(item) for item in engagement_facets(opportunity.opportunity_type)},
        "work_mode": {normalise_text(work_mode)} if work_mode else set(),
        "seniority": {normalise_text(seniority)} if seniority else set(),
        "work_style": {"execution only"} if is_execution_only(opportunity) else set(),
        "location": {normalise_text(opportunity.location)} if opportunity.location else set(),
    }


def _preference_matches(preference: WeightedPreference, facets: dict[str, set[str]]) -> bool:
    category, separator, raw_value = preference.key.casefold().partition(":")
    if not separator or category not in facets:
        return False
    value = normalise_text(raw_value)
    if not value or value in {"presented type", "flexibility"}:
        return False
    return any(value == candidate or value in candidate for candidate in facets[category])


def _preference_score(profile: PersonalProfile, opportunity: OpportunityProfile) -> tuple[float, str]:
    facets = _preference_facets(opportunity)
    matched = [preference for preference in profile.preferences if _preference_matches(preference, facets)]
    if not matched:
        return 0.5, "No directly matching engagement, work-mode, seniority, or work-style preference."

    values = [_directional_preference_value(preference) for preference in matched]
    score = sum(values) / len(values)
    keys = ", ".join(preference.key for preference in matched)
    direction = "positive affinity" if score >= 0.5 else "recorded aversion"
    return score, f"Applied {direction} from: {keys}."


def _candidate_values(opportunity: OpportunityProfile) -> set[str]:
    values = {
        opportunity.opportunity_type.value,
        opportunity.location or "",
        infer_work_mode(opportunity) or "",
        opportunity.seniority or infer_seniority(opportunity.title) or "",
        opportunity.title,
        *extract_concepts(_opportunity_values(opportunity)),
    }
    if is_execution_only(opportunity):
        values.add("execution_only")
    return {normalise_text(value) for value in values if value}


def _matches_rejected_value(rejected: str, candidate_values: set[str]) -> bool:
    normalised = normalise_text(rejected)
    if not normalised:
        return False
    return any(normalised == candidate or normalised in candidate for candidate in candidate_values)


def _constraint_score(profile: PersonalProfile, opportunity: OpportunityProfile) -> tuple[float, list[str], str]:
    candidate_values = _candidate_values(opportunity)
    hard_breaches: list[str] = []
    penalties = 0.0
    for constraint in profile.constraints:
        matched_rejections = sorted(
            value for value in constraint.rejected_values if _matches_rejected_value(value, candidate_values)
        )
        if not matched_rejections:
            continue
        if constraint.kind == ConstraintKind.HARD:
            hard_breaches.append(f"{constraint.key}: {', '.join(matched_rejections)}")
        else:
            penalties += constraint.penalty
    if hard_breaches:
        return 0.0, hard_breaches, "One or more hard constraints were violated."
    if penalties:
        return max(0.0, 1.0 - min(1.0, penalties)), [], "Applied matching soft-constraint penalties."
    return 1.0, [], "No hard or soft constraint violations detected."


def _future_direction_score(profile: PersonalProfile, opportunity: OpportunityProfile) -> tuple[float, str]:
    if not profile.aspirations:
        return 0.5, "No future direction has been recorded; neutral score applied."

    aspiration_values = [item.name for item in profile.aspirations]
    opportunity_values = _opportunity_values(opportunity)
    aspiration_tokens = meaningful_tokens(aspiration_values)
    opportunity_tokens = meaningful_tokens(opportunity_values)
    denominator = min(len(aspiration_tokens), len(opportunity_tokens))
    token_score = len(aspiration_tokens & opportunity_tokens) / denominator if denominator else 0.0

    aspiration_concepts = extract_concepts(aspiration_values)
    opportunity_concepts = extract_concepts(opportunity_values)
    concept_score = (
        len(aspiration_concepts & opportunity_concepts) / len(aspiration_concepts)
        if aspiration_concepts
        else 0.0
    )

    aspiration_text = normalise_text(" ".join(aspiration_values))
    engagement_score = 0.0
    if "consult" in aspiration_text or "fractional" in aspiration_text or "independent" in aspiration_text:
        if opportunity.opportunity_type in {
            opportunity.opportunity_type.CONSULTING,
            opportunity.opportunity_type.FRACTIONAL,
            opportunity.opportunity_type.ADVISORY,
        }:
            engagement_score = 0.90

    score = max(token_score, concept_score, engagement_score)
    return score, "Compared role direction, engagement model, and recognised problem areas with aspirations."


def _evidence_score(opportunity: OpportunityProfile) -> tuple[float, str]:
    if not opportunity.evidence:
        return 0.0, "No source-backed evidence was captured."
    source_confidence = sum(item.confidence for item in opportunity.evidence) / len(opportunity.evidence)
    score = (source_confidence * 0.60) + (opportunity.extraction_confidence * 0.40)
    return _clamp(score), "Combined source confidence with retained extraction confidence."


def calculate_fit(profile: PersonalProfile, opportunity: OpportunityProfile) -> FitScore:
    capability_score, capability_explanation = _capability_score(profile, opportunity)
    preference_score, preference_explanation = _preference_score(profile, opportunity)
    constraint_score, hard_breaches, constraint_explanation = _constraint_score(profile, opportunity)
    aspiration_score, aspiration_explanation = _future_direction_score(profile, opportunity)
    evidence_score, evidence_explanation = _evidence_score(opportunity)

    dimensions = [
        ScoreDimension(
            name="capability_fit",
            score=capability_score,
            weight=0.30,
            explanation=capability_explanation,
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
            explanation=aspiration_explanation,
        ),
        ScoreDimension(
            name="evidence_quality",
            score=evidence_score,
            weight=0.10,
            explanation=evidence_explanation,
        ),
    ]
    weighted = sum(dimension.score * dimension.weight for dimension in dimensions)
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
