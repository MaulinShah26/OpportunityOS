from opportunityos.application.factory import build_analysis_service
from opportunityos.config import Settings
from opportunityos.domain.enums import Decision
from opportunityos.domain.models import (
    AnalysisRequest,
    Aspiration,
    Capability,
    OpportunityInput,
    PersonalProfile,
    WeightedPreference,
)


def _maulin_like_profile() -> PersonalProfile:
    return PersonalProfile(
        display_name="Benchmark User",
        headline="Fractional Data and AI leader",
        capabilities=[
            Capability(name="artificial intelligence", proficiency=0.90),
            Capability(name="data science", proficiency=0.82),
            Capability(name="experimentation", proficiency=0.75),
            Capability(name="forecasting", proficiency=0.75),
            Capability(name="growth analytics", proficiency=0.70),
            Capability(name="product management", proficiency=0.75),
            Capability(name="retention analytics", proficiency=0.80),
            Capability(name="Python", proficiency=0.75),
            Capability(name="SQL", proficiency=0.75),
        ],
        preferences=[
            WeightedPreference(
                key="engagement:consulting",
                weight=0.60,
                explicit=True,
                confidence=0.90,
            ),
            WeightedPreference(
                key="seniority:junior",
                weight=0.44,
                explicit=True,
                confidence=0.90,
            ),
            WeightedPreference(
                key="work_style:execution_only",
                weight=0.45,
                explicit=True,
                confidence=0.90,
            ),
        ],
        aspirations=[
            Aspiration(name="AI product leadership", weight=0.90),
            Aspiration(name="independent consulting", weight=0.85),
        ],
        target_problem_areas=[
            "AI implementation",
            "Demand forecasting",
            "Growth optimisation",
            "Product strategy",
        ],
    )


def _analyse(raw_text: str):
    service = build_analysis_service(Settings(_env_file=None, llm_mode="mock"))
    return service.execute(
        AnalysisRequest(
            profile=_maulin_like_profile(),
            opportunity=OpportunityInput(raw_text=raw_text),
        )
    )


def test_consulting_engagement_without_role_field_is_extracted_and_pursued() -> None:
    result = _analyse(
        """Company: ZILO

Opportunity type: Independent consulting / fractional Data and AI engagement

The company operates in fashion retail with local, in-season selection across cities.

Potential business problems:
- Store-level assortment planning
- Demand forecasting
- Replenishment
- Translating online demand signals into local store inventory decisions
- Avoiding stockouts and excess inventory

The proposed engagement would involve identifying and implementing practical analytics or AI systems
that improve merchandising and inventory decisions.
"""
    )

    assert result.opportunity.title == "Independent consulting / fractional Data and AI engagement"
    assert result.opportunity.opportunity_type.value == "fractional"
    assert "Assortment planning" in result.opportunity.problem_areas
    assert "Inventory and replenishment" in result.opportunity.problem_areas
    assert result.opportunity.extraction_confidence >= 0.60
    assert result.recommendation.decision == Decision.PURSUE


def test_project_management_specialist_reaches_hold_instead_of_reject() -> None:
    result = _analyse(
        """Company: micro1
Role: Project Management Specialist
Opportunity type: Project-based AI training and evaluation work

The role evaluates end-to-end project management, planning, execution and delivery,
task, timeline and resource management, problem solving and risk handling,
communication, and understanding of AI.
"""
    )

    assert result.opportunity.title == "Project Management Specialist"
    assert result.opportunity.opportunity_type.value == "contract"
    assert "project management" in result.opportunity.required_skills
    assert "risk management" in result.opportunity.required_skills
    assert result.recommendation.decision == Decision.HOLD


def test_unqualified_execution_heavy_analyst_role_is_rejected() -> None:
    result = _analyse(
        """Company: genbrothers
Role: Data Analyst (Excel Power Query)
Opportunity type: Full-time
Responsibilities: Excel reporting, Power Query, dashboard production and report generation.
"""
    )

    assert result.opportunity.seniority == "junior"
    preference_dimension = next(
        item for item in result.fit_score.dimensions if item.name == "preference_fit"
    )
    assert preference_dimension.score < 0.30
    assert result.recommendation.decision == Decision.REJECT


def test_single_high_confidence_pasted_source_is_not_treated_as_weak_evidence() -> None:
    result = _analyse(
        """Company: Acme
Role: Senior Product Manager - Consultant
Opportunity type: Consulting
Need product management, product strategy, AI implementation and stakeholder communication.
"""
    )

    evidence_dimension = next(
        item for item in result.fit_score.dimensions if item.name == "evidence_quality"
    )
    assert len(result.opportunity.evidence) == 1
    assert evidence_dimension.score >= 0.80
