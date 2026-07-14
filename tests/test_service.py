from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.enums import Decision
from opportunityos.domain.models import AnalysisRequest, OpportunityInput, PersonalProfile
from opportunityos.infrastructure.llm.mock import (
    MockBusinessAnalyst,
    MockOpportunityExtractor,
    MockOutreachWriter,
)
from opportunityos.infrastructure.research import InputOnlyResearchProvider


def test_vertical_slice_produces_grounded_result(strong_profile: PersonalProfile) -> None:
    service = AnalyseOpportunityService(
        research=InputOnlyResearchProvider(),
        extractor=MockOpportunityExtractor(),
        analyst=MockBusinessAnalyst(),
        outreach_writer=MockOutreachWriter(),
    )
    result = service.execute(
        AnalysisRequest(
            profile=strong_profile,
            opportunity=OpportunityInput(
                raw_text=(
                    "Company: Acme Consumer\n"
                    "Role: Fractional Data and AI Lead\n"
                    "Location: Remote\n"
                    "Need product analytics, retention and AI support."
                )
            ),
        )
    )
    assert result.opportunity.company_name == "Acme Consumer"
    assert result.opportunity.evidence
    assert result.hypotheses
    assert result.recommendation.decision in {Decision.PURSUE, Decision.HOLD}
    if result.recommendation.decision == Decision.PURSUE:
        assert result.outreach is not None
