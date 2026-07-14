from opportunityos.application.onboarding import build_profile_from_resume
from opportunityos.domain.models import ResumeOnboardingRequest


def test_resume_onboarding_extracts_capabilities_and_problem_areas() -> None:
    request = ResumeOnboardingRequest(
        display_name="Test User",
        headline="Data and AI operator",
        resume_text=(
            "Senior Data Scientist\n"
            "Built product analytics, retention cohorts, growth funnels and AI innovation systems.\n"
            "Used Python, SQL and experimentation to improve conversion."
        ),
    )
    profile, capabilities, problem_areas = build_profile_from_resume(request)
    assert profile.display_name == "Test User"
    assert "product analytics" in capabilities
    assert "retention" in problem_areas
    assert "growth" in problem_areas


def test_resume_onboarding_keeps_explicit_profile_fields() -> None:
    request = ResumeOnboardingRequest(
        display_name="Test User",
        headline="Fractional leader",
        resume_text="Data scientist with more than ten years of product analytics experience.",
        target_problem_areas=["custom priority"],
    )
    profile, _, problem_areas = build_profile_from_resume(request)
    assert profile.headline == "Fractional leader"
    assert problem_areas[0] == "custom priority"
