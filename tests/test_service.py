from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.domain.enums import Decision
from opportunityos.domain.models import AnalysisRequest,OpportunityInput,PersonalProfile
from opportunityos.infrastructure.llm.mock import MockBusinessAnalyst,MockOpportunityExtractor,MockOutreachWriter
from opportunityos.infrastructure.research import InputOnlyResearchProvider
def test_vertical_slice_produces_grounded_result(strong_profile:PersonalProfile):
    s=AnalyseOpportunityService(InputOnlyResearchProvider(),MockOpportunityExtractor(),MockBusinessAnalyst(),MockOutreachWriter());r=s.execute(AnalysisRequest(profile=strong_profile,opportunity=OpportunityInput(raw_text='Company: Acme Consumer\nRole: Fractional Data and AI Lead\nLocation: Remote\nNeed product analytics, retention and AI support.')));assert r.opportunity.company_name=='Acme Consumer';assert r.opportunity.evidence;assert r.hypotheses;assert r.recommendation.decision in {Decision.PURSUE,Decision.HOLD}
