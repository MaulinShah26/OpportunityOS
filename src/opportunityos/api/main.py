from __future__ import annotations

from fastapi import Depends, FastAPI

from opportunityos.application.learning import apply_feedback
from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.config import get_settings
from opportunityos.domain.models import (
    AnalysisRequest,
    AnalysisResult,
    FeedbackRequest,
    FeedbackResponse,
)
from opportunityos.orchestration.crewai_runtime import execute_with_crewai
from opportunityos.api.dependencies import get_analysis_service

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Personal opportunity intelligence vertical slice",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_mode": settings.llm_mode,
        "orchestrator": settings.orchestrator,
    }


@app.post("/v1/analyses", response_model=AnalysisResult)
def analyse_opportunity(
    request: AnalysisRequest,
    service: AnalyseOpportunityService = Depends(get_analysis_service),
) -> AnalysisResult:
    if settings.orchestrator == "crewai":
        return execute_with_crewai(service, request)
    return service.execute(request)


@app.post("/v1/feedback", response_model=FeedbackResponse)
def record_feedback(request: FeedbackRequest) -> FeedbackResponse:
    updated, changes = apply_feedback(
        request.profile,
        request.feedback,
        opportunity_type=request.opportunity_type,
        company_industry=request.company_industry,
    )
    return FeedbackResponse(updated_profile=updated, applied_updates=changes)
