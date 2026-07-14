from __future__ import annotations

from opportunityos.application.ports import BusinessAnalyst, OpportunityExtractor, OutreachWriter, ResearchProvider
from opportunityos.application.scoring import calculate_fit, recommend
from opportunityos.domain.enums import Decision
from opportunityos.domain.models import AnalysisRequest, AnalysisResult


class AnalyseOpportunityService:
    def __init__(self, research: ResearchProvider, extractor: OpportunityExtractor, analyst: BusinessAnalyst, outreach_writer: OutreachWriter, *, orchestrator_name: str = "local", model_metadata: dict[str, str] | None = None) -> None:
        self._research = research
        self._extractor = extractor
        self._analyst = analyst
        self._outreach_writer = outreach_writer
        self._orchestrator_name = orchestrator_name
        self._model_metadata = model_metadata or {}

    def execute(self, request: AnalysisRequest) -> AnalysisResult:
        evidence = self._research.collect(request.opportunity)
        opportunity = self._extractor.extract(request.opportunity, evidence)
        hypotheses = self._analyst.analyse(request.profile, opportunity)
        fit_score = calculate_fit(request.profile, opportunity)
        recommendation = recommend(fit_score, opportunity)
        outreach = None
        if recommendation.decision == Decision.PURSUE:
            outreach = self._outreach_writer.draft(request.profile, opportunity, hypotheses)
        return AnalysisResult(opportunity=opportunity, hypotheses=hypotheses, fit_score=fit_score, recommendation=recommendation, outreach=outreach, orchestrator=self._orchestrator_name, model_metadata=self._model_metadata)
