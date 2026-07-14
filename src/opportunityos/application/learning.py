from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from opportunityos.domain.enums import FeedbackAction, FeedbackReason, OpportunityType
from opportunityos.domain.models import FeedbackEvent, PersonalProfile, WeightedPreference

EXPLICIT_MULTIPLIER = 1.0
IMPLICIT_MULTIPLIER = 0.35
MAX_SINGLE_UPDATE = 0.08


def _find_or_create(profile: PersonalProfile, key: str) -> WeightedPreference:
    for preference in profile.preferences:
        if preference.key == key:
            return preference
    preference = WeightedPreference(key=key, weight=0.5, explicit=False, confidence=0.4)
    profile.preferences.append(preference)
    return preference


def _bounded_update(preference: WeightedPreference, delta: float, explicit: bool) -> None:
    multiplier = EXPLICIT_MULTIPLIER if explicit else IMPLICIT_MULTIPLIER
    applied = max(-MAX_SINGLE_UPDATE, min(MAX_SINGLE_UPDATE, delta * multiplier))
    preference.weight = max(0.0, min(1.0, preference.weight + applied))
    preference.confidence = max(
        preference.confidence,
        0.9 if explicit else min(0.8, preference.confidence + 0.05),
    )
    preference.explicit = preference.explicit or explicit
    preference.last_updated_at = datetime.now(timezone.utc)


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
    direction = 1.0 if feedback.action in positive_actions else -1.0 if feedback.action in negative_actions else 0.0

    if opportunity_type and direction:
        key = f"engagement:{opportunity_type.value}"
        pref = _find_or_create(updated, key)
        _bounded_update(pref, 0.05 * direction, feedback.explicit)
        changes.append(f"Updated {key} to {pref.weight:.2f}")

    if company_industry and direction:
        key = f"industry:{company_industry.strip().lower()}"
        pref = _find_or_create(updated, key)
        _bounded_update(pref, 0.03 * direction, feedback.explicit)
        changes.append(f"Updated {key} to {pref.weight:.2f}")

    reason_updates = {
        FeedbackReason.LOCATION_MISMATCH: ("location:flexibility", -0.05),
        FeedbackReason.TOO_EXECUTION_HEAVY: ("work_style:execution_only", -0.05),
        FeedbackReason.TOO_JUNIOR: ("seniority:junior", -0.06),
        FeedbackReason.STRONG_FIT: ("recommendation:similar_profiles", 0.04),
        FeedbackReason.WRONG_ENGAGEMENT: ("engagement:presented_type", -0.05),
    }
    for reason in feedback.reasons:
        if reason not in reason_updates:
            continue
        key, delta = reason_updates[reason]
        pref = _find_or_create(updated, key)
        _bounded_update(pref, delta, feedback.explicit)
        changes.append(f"Updated {key} to {pref.weight:.2f}")

    return updated, changes
