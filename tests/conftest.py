import pytest

from opportunityos.domain.enums import ConstraintKind
from opportunityos.domain.models import (
    Aspiration,
    Capability,
    Constraint,
    PersonalProfile,
    WeightedPreference,
)


@pytest.fixture
def strong_profile() -> PersonalProfile:
    return PersonalProfile(
        display_name="Test User",
        headline="Fractional Data and AI leader",
        capabilities=[
            Capability(name="product analytics", proficiency=0.9),
            Capability(name="retention", proficiency=0.9),
            Capability(name="ai", proficiency=0.8),
        ],
        preferences=[
            WeightedPreference(key="fractional", weight=0.95),
            WeightedPreference(key="remote", weight=0.9),
        ],
        constraints=[
            Constraint(
                key="onsite restriction",
                kind=ConstraintKind.HARD,
                rejected_values=["onsite"],
            )
        ],
        aspirations=[Aspiration(name="data ai leadership", weight=0.9)],
    )
