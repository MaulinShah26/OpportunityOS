from uuid import uuid4

import pytest

from opportunityos.application.learning import apply_feedback
from opportunityos.application.onboarding import build_profile_from_resume
from opportunityos.domain.enums import FeedbackAction, FeedbackReason, MemoryAction, MemoryCategory
from opportunityos.domain.models import (
    Capability,
    FeedbackEvent,
    MemoryMutationRequest,
    PersonalProfile,
    ResumeOnboardingRequest,
    WeightedPreference,
)
from opportunityos.domain.taxonomy import (
    canonicalise_problem_areas,
    preference_display_label,
)
from opportunityos.infrastructure.database import Database, MemoryConflictError, SqlAlchemyStore


def test_problem_areas_are_case_insensitive_and_business_focused() -> None:
    assert canonicalise_problem_areas(
        [
            "AI Implementation",
            "ai implementation",
            "data science",
            "forecasting",
            "retention",
        ]
    ) == [
        "AI implementation",
        "Demand forecasting",
        "Retention improvement",
    ]


def test_onboarding_does_not_copy_capability_names_into_problem_areas() -> None:
    profile, capabilities, problem_areas = build_profile_from_resume(
        ResumeOnboardingRequest(
            display_name="Memory Quality User",
            headline="Data and AI leader",
            resume_text=(
                "Senior data scientist who built AI innovation, forecasting, experimentation, "
                "growth funnels and retention cohorts using Python and SQL."
            ),
            target_problem_areas=["AI Implementation"],
        )
    )

    assert "data science" in capabilities
    assert "data science" not in problem_areas
    assert problem_areas.count("AI implementation") == 1
    assert "Demand forecasting" in profile.target_problem_areas
    assert "Experimentation systems" in profile.target_problem_areas


def test_profile_persistence_canonicalises_duplicates_and_preference_aliases() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    profile = PersonalProfile(
        display_name="Canonical User",
        headline="Data and AI operator",
        capabilities=[Capability(name="data science", proficiency=0.8)],
        preferences=[
            WeightedPreference(
                key="recommendation:similar_profiles",
                weight=0.58,
                explicit=True,
                confidence=0.9,
            ),
            WeightedPreference(
                key="recommendation:similar_opportunities",
                weight=0.55,
                explicit=False,
                confidence=0.5,
            ),
        ],
        target_problem_areas=[
            "AI Implementation",
            "ai implementation",
            "data science",
            "growth",
        ],
    )

    with database.session() as session:
        store = SqlAlchemyStore(session)
        saved = store.save_profile(profile, actor="profile_user")
        assert saved.target_problem_areas == ["AI implementation", "Growth optimisation"]
        assert [item.key for item in saved.preferences] == ["recommendation:similar_opportunities"]

        memory = store.list_memory(saved.user_id)
        problem_keys = [item.key for item in memory if item.category == MemoryCategory.PROBLEM_AREA]
        preference_keys = [item.key for item in memory if item.category == MemoryCategory.PREFERENCE]
        assert problem_keys == ["AI implementation", "Growth optimisation"]
        assert preference_keys == ["recommendation:similar_opportunities"]


def test_feedback_uses_human_readable_canonical_preference() -> None:
    profile = PersonalProfile(
        display_name="Feedback User",
        headline="Product leader",
        capabilities=[Capability(name="product management", proficiency=0.8)],
    )
    updated, _ = apply_feedback(
        profile,
        FeedbackEvent(
            analysis_id=uuid4(),
            action=FeedbackAction.PURSUE,
            reasons=[FeedbackReason.STRONG_FIT],
        ),
    )
    assert updated.preferences[0].key == "recommendation:similar_opportunities"
    assert (
        preference_display_label(updated.preferences[0].key)
        == "Opportunities similar to ones I marked worth pursuing"
    )


def test_problem_area_editor_rejects_capability_only_values() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.create_schema()
    profile = PersonalProfile(
        display_name="Editor User",
        headline="AI operator",
        capabilities=[Capability(name="artificial intelligence", proficiency=0.8)],
        target_problem_areas=["AI implementation"],
    )

    with database.session() as session:
        store = SqlAlchemyStore(session)
        store.save_profile(profile)
        problem = next(
            item
            for item in store.list_memory(profile.user_id)
            if item.category == MemoryCategory.PROBLEM_AREA
        )
        with pytest.raises(MemoryConflictError, match="business problem"):
            store.mutate_memory(
                profile.user_id,
                problem.id,
                MemoryMutationRequest(
                    action=MemoryAction.UPDATE,
                    key="data science",
                    value={"name": "data science"},
                ),
            )
