from __future__ import annotations

from opportunityos.application.grounding import ground_extracted_opportunity
from opportunityos.application.guardrails import evaluate_guardrails
from opportunityos.application.ports import (
    BusinessAnalyst,
    ModelRuntime,
    OpportunityExtractor,
    OutreachWriter,
    ResearchProvider,
)
from opportunityos.application.scoring import calculate_fit, recommend
from opportunityos.domain.enums import CriticSeverity, Decision
from opportunityos.domain.models import AnalysisRequest, AnalysisResult, GuardrailIssue


class AnalyseOpportunityService:
    def __init__(
        self,
        research: ResearchProvider,
        extractor: OpportunityExtractor,
        analyst: BusinessAnalyst,
        outreach_writer: OutreachWriter,
        *,
        orchestrator_name: str = "local",
        model_metadata: dict[str, str] | None = None,
        model_runtime: ModelRuntime | None = None,
    ) -> None:
        self._research = research
        self._extractor = extractor
        self._analyst = analyst
        self._outreach_writer = outreach_writer
        self._orchestrator_name = orchestrator_name
        self._model_metadata = model_metadata or {}
        self._model_runtime = model_runtime

    def execute(self, request: AnalysisRequest) -> AnalysisResult:
        if self._model_runtime is not None:
            self._model_runtime.start_run()

        evidence = self._research.collect(request.opportunity)
        extracted = self._extractor.extract(request.opportunity, evidence)
        opportunity, grounding_issues = ground_extracted_opportunity(
            request.opportunity,
            evidence,
            extracted,
        )
        hypotheses = self._analyst.analyse(request.profile, opportunity)
        fit_score = calculate_fit(request.profile, opportunity)
        recommendation = recommend(fit_score, opportunity)
        outreach = None
        runtime_issues = list(grounding_issues)
        if recommendation.decision == Decision.PURSUE:
            try:
                outreach = self._outreach_writer.draft(request.profile, opportunity, hypotheses)
            except Exception as exc:
                runtime_issues.append(
                    GuardrailIssue(
                        code="outreach_generation_unavailable",
                        message="The decision is available, but live outreach generation failed safely.",
                        severity=CriticSeverity.WARNING,
                        claim=type(exc).__name__,
                    )
                )
        critic = evaluate_guardrails(
            opportunity,
            hypotheses,
            recommendation,
            outreach,
            initial_issues=runtime_issues,
        )
        if critic.block_outreach:
            outreach = None

        metadata = dict(self._model_metadata)
        if self._model_runtime is not None:
            metadata.update(self._model_runtime.metadata())

        return AnalysisResult(
            opportunity=opportunity,
            hypotheses=hypotheses,
            fit_score=fit_score,
            recommendation=recommendation,
            outreach=outreach,
            critic=critic,
            orchestrator=self._orchestrator_name,
            model_metadata=metadata,
        )
