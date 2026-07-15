from opportunityos.application.factory import build_analysis_service
from opportunityos.config import Settings
from opportunityos.domain.enums import Decision, OpportunityType
from opportunityos.domain.models import (
    AnalysisRequest,
    Aspiration,
    Capability,
    OpportunityInput,
    PersonalProfile,
    WeightedPreference,
)


def _profile() -> PersonalProfile:
    return PersonalProfile(
        display_name="Source Fidelity User",
        headline="Fractional Data and AI leader",
        capabilities=[
            Capability(name="artificial intelligence", proficiency=0.90),
            Capability(name="data science", proficiency=0.82),
            Capability(name="forecasting", proficiency=0.75),
            Capability(name="product management", proficiency=0.75),
            Capability(name="SQL", proficiency=0.75),
        ],
        preferences=[
            WeightedPreference(
                key="engagement:consulting",
                weight=0.60,
                explicit=True,
                confidence=0.90,
            )
        ],
        aspirations=[Aspiration(name="independent consulting", weight=0.90)],
    )


def _analyse(raw_text: str):
    service = build_analysis_service(Settings(_env_file=None, llm_mode="mock"))
    return service.execute(
        AnalysisRequest(
            profile=_profile(),
            opportunity=OpportunityInput(raw_text=raw_text),
        )
    )


def test_company_partner_language_does_not_become_partnership_engagement() -> None:
    result = _analyse(
        """Role : Data Analyst (Excel Power Query)
About Penbrothers
Penbrothers is a remote talent management partner serving high-growth companies.
About the Client
The company fosters strong partnerships within its industry.
About the Role
Support existing technology processes and improve data reliability.
What You'll Do
Translate data into actionable insights. Build reports and dashboards with advanced Excel.
What you Bring
Operate independently as a data analyst. Use Power Query and communicate with stakeholders.
Experience with AI-driven initiatives is useful.
Nice to Have
SQL foundation.
Our Hiring Process
Candidates meet an AI interviewer.
What You'll Get
Opportunities for professional growth.
"""
    )

    assert result.opportunity.title == "Data Analyst (Excel Power Query)"
    assert result.opportunity.opportunity_type == OpportunityType.UNKNOWN
    assert "growth" not in result.opportunity.required_skills
    assert "Growth optimisation" not in result.opportunity.problem_areas
    assert "analytics" in result.opportunity.required_skills
    assert result.recommendation.decision == Decision.REJECT
    assert "junior_execution_only_role" in result.model_metadata["decision_gates"]
    assert not any(
        issue.code == "unsupported_extracted_value" and issue.claim == "analytics"
        for issue in result.critic.issues
    )


def test_concrete_advisory_headline_is_extracted_and_capability_gap_caps_pursue() -> None:
    result = _analyse(
        """Expert Opportunity - Advisory Consultant ($80/hr, up to $1,600/week)
About This Opportunity
Help a foundational AI lab evaluate professional presentations and slide-deck tasks.
Qualifications
Four years at a top advisory or strategy practice. Expert PowerPoint and slide craftsmanship.
Strong client-deliverable structure, storylining, data exhibits, and written communication.
About Ethos
Ethos connects experts with investors and consultancies.
Key Requirements
Advisory consulting experience, PowerPoint, storylining, and communication.
Location: Fully remote
"""
    )

    assert result.opportunity.title == "Advisory Consultant"
    assert result.opportunity.opportunity_type == OpportunityType.ADVISORY
    assert "PowerPoint" in result.opportunity.required_skills
    assert "storylining" in result.opportunity.required_skills
    assert "advisory consulting" in result.opportunity.required_skills
    assert result.model_metadata["score_based_decision"] == Decision.PURSUE.value
    assert "insufficient_capability_coverage" in result.model_metadata["decision_gates"]
    assert "insufficient_opportunity_identity" not in result.model_metadata["decision_gates"]
    assert result.recommendation.decision == Decision.HOLD


def test_explicit_full_time_type_still_outranks_partnership_boilerplate() -> None:
    result = _analyse(
        """Company: Acme
Role: Data Analyst
Opportunity type: Full-time
About the company
Acme is a trusted technology partner and values long-term partnerships.
Responsibilities
Build Excel reports and maintain dashboards.
"""
    )

    assert result.opportunity.opportunity_type == OpportunityType.FULL_TIME
