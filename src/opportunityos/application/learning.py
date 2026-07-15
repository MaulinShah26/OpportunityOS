from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from opportunityos.domain.enums import FeedbackAction, FeedbackReason, OpportunityType
from opportunityos.domain.models import FeedbackEvent, PersonalProfile, WeightedPreference
from opportunityos.domain.taxonomy import canonicalise_preference_key

EXPLICIT_MULTIPLIER = 1.0
IMPLICIT_MULTIPLIER = 0.35
MAX_SINGLE_UPDATE = 0.08


def _find_or_create(profile: PersonalProfile, key: str) -> WeightedPreference:
    canonical_key = canonicalise_preference_key(key)
    for preference in profile.preferences:
        if canonicalise_preference_key(preference.key) == canonical_key:
            preference.key = canonical_key
            return preference
    preference = WeightedPreference(key=canonical_key, weight=0.5, explicit=False, confidence=0.4)
    profile.preferences.append(preference)
    return preference


def _bounded_update(preference: WeightedPreference, delta: float, explicit: bool) -> bool:
    if preference.explicit and not explicit:
        return False
    multiplier = EXPLICIT_MULTIPLIER if explicit else IMPLICIT_MULTIPLIER
    applied = max(-MAX_SINGLE_UPDATE, min(MAX_SINGLE_UPDATE, delta * multiplier))
    preference.weight = max(0.0, min(1.0, preference.weight + applied))
    preference.confidence = max(
        preference.confidence,
        0.9 if explicit else min(0.8, preference.confidence + 0.05),
    )
    preference.explicit = preference.explicit or explicit
    preference.last_updated_at = datetime.now(timezone.utc)
    return True


def _apply_preference_update(
    profile: PersonalProfile,
    changes: list[str],
    *,
    key: str,
    delta: float,
    explicit: bool,
) -> None:
    preference = _find_or_create(profile, key)
    if _bounded_update(preference, delta, explicit):
        changes.append(f"Updated {preference.key} to {preference.weight:.2f}")
    else:
        changes.append(f"Preserved explicit {preference.key}")


def apply_feedback(
    profile: PersonalProfile,
    feedback: FeedbackEvent,
    opportunity_type: OpportunityType | None = None,
    company_industry: str | None = None,
) -> tuple[PersonalProfile, list[str]]:
    updated = deepcopy(profile)
    changes: list[str] = []

    positive_actions = {FeedbackAction.RELEVANT, FeedbackAction.SAVE, FeedbackAction.PURSUE}
    negative_actions = {FeedbackAction.NOT_RELEVANT, FeedbackAction.REJECT}
    positive = feedback.action in positive_actions
    negative = feedback.action in negative_actions
    legacy_unexplained_negative = negative and not feedback.reasons

    engagement_direction = 1.0 if positive else -1.0 if (
        legacy_unexplained_negative or FeedbackReason.WRONG_ENGAGEMENT in feedback.reasons
    ) else 0.0
    if opportunity_type and engagement_direction:
        _apply_preference_update(
            updated,
            changes,
            key=f"engagement:{opportunity_type.value}",
            delta=0.05 * engagement_direction,
            explicit=feedback.explicit,
        )

    industry_direction = 1.0 if positive else -1.0 if (
        legacy_unexplained_negative or FeedbackReason.WRONG_COMPANY in feedback.reasons
    ) else 0.0
    if company_industry and industry_direction:
        _apply_preference_update(
            updated,
            changes,
            key=f"industry:{company_industry.strip().lower()}",
            delta=0.03 * industry_direction,
            explicit=feedback.explicit,
        )

    reason_updates = {
        FeedbackReason.LOCATION_MISMATCH: ("location:flexibility", -0.05),
        FeedbackReason.TOO_EXECUTION_HEAVY: ("work_style:execution_only", -0.06),
        FeedbackReason.LOW_OWNERSHIP: ("work_style:low_ownership", -0.06),
        FeedbackReason.TOO_JUNIOR: ("seniority:junior", -0.06),
        FeedbackReason.STRONG_FIT: ("recommendation:similar_opportunities", 0.04),
        FeedbackReason.WRONG_ENGAGEMENT: ("engagement:presented_type", -0.05),
    }
    for reason in feedback.reasons:
        if reason not in reason_updates:
            continue
        key, delta = reason_updates[reason]
        _apply_preference_update(
            updated,
            changes,
            key=key,
            delta=delta,
            explicit=feedback.explicit,
        )

    return updated, changes
