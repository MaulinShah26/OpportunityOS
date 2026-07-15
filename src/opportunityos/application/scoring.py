from __future__ import annotations

from opportunityos.domain.enums import ConstraintKind, Decision, OpportunityType
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
    has_generic_opportunity_title,
    infer_seniority,
    infer_work_mode,
    is_execution_only,
    is_low_ownership,
    meaningful_tokens,
    normalise_text,
)

DEFAULT_HOLD_THRESHOLD = 45
DEFAULT_PURSUE_THRESHOLD = 72
DEFAULT_MIN_EXTRACTION_CONFIDENCE = 0.60

GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY = "insufficient_opportunity_identity"
GATE_JUNIOR_EXECUTION_ONLY = "junior_execution_only_role"
GATE_EXPLICIT_LOW_OWNERSHIP_AVERSION = "explicit_low_ownership_aversion"

_REJECT_GATES = {
    GATE_JUNIOR_EXECUTION_ONLY,
    GATE_EXPLICIT_LOW_OWNERSHIP_AVERSION,
}


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
    work_styles: set[str] = set()
    if is_execution_only(opportunity):
        work_styles.add("execution only")
    if is_low_ownership(opportunity):
        work_styles.add("low ownership")
    return {
        "engagement": {normalise_text(item) for item in engagement_facets(opportunity.opportunity_type)},
        "work_mode": {normalise_text(work_mode)} if work_mode else set(),
        "seniority": {normalise_text(seniority)} if seniority else set(),
        "work_style": work_styles,
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
    if is_low_ownership(opportunity):
        values.add("low_ownership")
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
    wants_independent_work = (
        "consult" in aspiration_text or "fractional" in aspiration_text or "independent" in aspiration_text
    )
    if wants_independent_work and opportunity.opportunity_type in {
        OpportunityType.CONSULTING,
        OpportunityType.FRACTIONAL,
        OpportunityType.ADVISORY,
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
    """Apply the score and confidence thresholds without user-specific decision gates."""
    if has_hard_constraint_breach:
        return Decision.REJECT
    if fit_total >= pursue_threshold and extraction_confidence >= min_extraction_confidence:
        return Decision.PURSUE
    if fit_total >= hold_threshold:
        return Decision.HOLD
    return Decision.REJECT


def _explicit_preference(profile: PersonalProfile | None, key: str) -> WeightedPreference | None:
    if profile is None:
        return None
    normalised_key = key.casefold()
    return next(
        (
            preference
            for preference in profile.preferences
            if preference.explicit and preference.key.casefold() == normalised_key
        ),
        None,
    )


def decision_gate_codes(
    profile: PersonalProfile | None,
    opportunity: OpportunityProfile,
) -> list[str]:
    gates: list[str] = []
    if has_generic_opportunity_title(opportunity):
        gates.append(GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY)

    seniority = opportunity.seniority or infer_seniority(opportunity.title)
    execution_preference = _explicit_preference(profile, "work_style:execution_only")
    execution_override = bool(execution_preference and execution_preference.weight >= 0.65)
    if seniority in {"intern", "junior", "associate"} and is_execution_only(opportunity) and not execution_override:
        gates.append(GATE_JUNIOR_EXECUTION_ONLY)

    low_ownership_preference = _explicit_preference(profile, "work_style:low_ownership")
    if (
        low_ownership_preference
        and low_ownership_preference.weight <= 0.40
        and is_low_ownership(opportunity)
    ):
        gates.append(GATE_EXPLICIT_LOW_OWNERSHIP_AVERSION)
    return gates


def apply_decision_gate_codes(decision: Decision, gate_codes: list[str]) -> Decision:
    if any(code in _REJECT_GATES for code in gate_codes):
        return Decision.REJECT
    if GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY in gate_codes and decision == Decision.PURSUE:
        return Decision.HOLD
    return decision


def decision_trace(
    profile: PersonalProfile | None,
    fit: FitScore,
    opportunity: OpportunityProfile,
) -> tuple[Decision, list[str], Decision]:
    score_decision = decision_for_thresholds(
        fit_total=fit.total,
        extraction_confidence=opportunity.extraction_confidence,
        has_hard_constraint_breach=bool(fit.hard_constraint_breaches),
    )
    gates = decision_gate_codes(profile, opportunity)
    return score_decision, gates, apply_decision_gate_codes(score_decision, gates)


def recommend(
    fit: FitScore,
    opportunity: OpportunityProfile,
    profile: PersonalProfile | None = None,
) -> Recommendation:
    score_decision, gates, decision = decision_trace(profile, fit, opportunity)
    if fit.hard_constraint_breaches:
        return Recommendation(
            decision=Decision.REJECT,
            rationale="The opportunity violates a user-defined hard constraint.",
            risks=fit.hard_constraint_breaches,
            next_action="Do not pursue unless the user explicitly changes the relevant constraint.",
        )
    if GATE_JUNIOR_EXECUTION_ONLY in gates:
        return Recommendation(
            decision=Decision.REJECT,
            rationale=(
                "The role is both junior or unqualified and dominated by execution or reporting work, "
                "so it is directionally weaker than the user's current path."
            ),
            risks=["Low ownership and seniority may make this a poor use of attention."],
            next_action="Archive it, or override the work-style preference explicitly if this role is exceptional.",
        )
    if GATE_EXPLICIT_LOW_OWNERSHIP_AVERSION in gates:
        return Recommendation(
            decision=Decision.REJECT,
            rationale="The opportunity conflicts with an explicit learned aversion to low-ownership work.",
            risks=["The role appears to repeat a work pattern the user previously rejected."],
            next_action="Archive it unless the source shows materially greater ownership than currently described.",
        )
    if GATE_INSUFFICIENT_OPPORTUNITY_IDENTITY in gates and score_decision == Decision.PURSUE:
        return Recommendation(
            decision=Decision.HOLD,
            rationale=(
                "The score is promising, but the source does not identify a concrete role or engagement clearly "
                "enough for a pursue recommendation."
            ),
            risks=["The opportunity identity is incomplete, so the apparent fit may be misleading."],
            next_action="Collect a concrete role, engagement type, or business brief before deciding to pursue.",
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
