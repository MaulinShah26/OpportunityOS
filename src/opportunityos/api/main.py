from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.staticfiles import StaticFiles

from opportunityos.api.dependencies import get_analysis_service, get_store
from opportunityos.application.learning import apply_feedback
from opportunityos.application.onboarding import build_profile_from_resume
from opportunityos.application.service import AnalyseOpportunityService
from opportunityos.config import get_settings
from opportunityos.domain.enums import Decision, FeedbackAction, OpportunityType
from opportunityos.domain.models import (
    AnalysisRequest,
    AnalysisResult,
    FeedbackRequest,
    FeedbackResponse,
    MemoryAuditCollection,
    MemoryCollection,
    MemoryItem,
    MemoryMutationRequest,
    PersistedAnalysisRequest,
    PersistedFeedbackRequest,
    PersonalProfile,
    ProfileResponse,
    ResumeOnboardingRequest,
    UserActivitySummary,
)
from opportunityos.infrastructure.database import (
    AnalysisNotFoundError,
    MemoryConflictError,
    MemoryNotFoundError,
    ProfileNotFoundError,
    SqlAlchemyStore,
)
from opportunityos.infrastructure.resume import UnsupportedResumeError, extract_resume_text
from opportunityos.orchestration.crewai_runtime import execute_with_crewai
from opportunityos.web.routes import STATIC_ROOT
from opportunityos.web.routes import router as web_router

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description="Personal opportunity intelligence with a user-controlled web workspace",
)
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
app.include_router(web_router)


def _execute_analysis(
    service: AnalyseOpportunityService,
    request: AnalysisRequest,
) -> AnalysisResult:
    if settings.orchestrator == "crewai":
        return execute_with_crewai(service, request)
    return service.execute(request)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_mode": settings.llm_mode,
        "orchestrator": settings.orchestrator,
    }


@app.post("/v1/profiles", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def save_profile(
    profile: PersonalProfile,
    email: str | None = None,
    store: SqlAlchemyStore = Depends(get_store),
) -> ProfileResponse:
    saved = store.save_profile(profile, email=email, actor="profile_user", reason="profile update")
    return ProfileResponse(profile=saved, email=email)


@app.post(
    "/v1/profiles/onboard",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def onboard_profile(
    request: ResumeOnboardingRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> ProfileResponse:
    profile, capabilities, problem_areas = build_profile_from_resume(request)
    store.save_profile(profile, email=request.email)
    return ProfileResponse(
        profile=profile,
        email=request.email,
        inferred_capabilities=capabilities,
        inferred_problem_areas=problem_areas,
    )


@app.post(
    "/v1/profiles/onboard-file",
    response_model=ProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def onboard_profile_file(
    display_name: Annotated[str, Form(min_length=2, max_length=160)],
    file: Annotated[UploadFile, File(description="A .txt, .pdf, or .docx resume")],
    headline: Annotated[str | None, Form(max_length=300)] = None,
    email: Annotated[str | None, Form(max_length=320)] = None,
    store: SqlAlchemyStore = Depends(get_store),
) -> ProfileResponse:
    try:
        resume_text = extract_resume_text(file.filename or "resume.txt", await file.read())
    except UnsupportedResumeError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    request = ResumeOnboardingRequest(
        display_name=display_name,
        headline=headline,
        email=email,
        resume_text=resume_text,
    )
    profile, capabilities, problem_areas = build_profile_from_resume(request)
    store.save_profile(profile, email=email)
    return ProfileResponse(
        profile=profile,
        email=email,
        inferred_capabilities=capabilities,
        inferred_problem_areas=problem_areas,
    )


@app.get("/v1/profiles/{user_id}", response_model=ProfileResponse)
def read_profile(
    user_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> ProfileResponse:
    try:
        return ProfileResponse(profile=store.get_profile(user_id))
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc


@app.get("/v1/users/{user_id}/memory", response_model=MemoryCollection)
def read_user_memory(
    user_id: UUID,
    include_inactive: bool = False,
    store: SqlAlchemyStore = Depends(get_store),
) -> MemoryCollection:
    try:
        store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    return MemoryCollection(
        user_id=user_id,
        items=store.list_memory(user_id, include_inactive=include_inactive),
    )


@app.patch("/v1/users/{user_id}/memory/{memory_id}", response_model=MemoryItem)
def mutate_user_memory(
    user_id: UUID,
    memory_id: UUID,
    request: MemoryMutationRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> MemoryItem:
    try:
        return store.mutate_memory(user_id, memory_id, request)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory item not found") from exc
    except MemoryConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.delete(
    "/v1/users/{user_id}/memory/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user_memory(
    user_id: UUID,
    memory_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> None:
    try:
        store.delete_memory(user_id, memory_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory item not found") from exc
    except MemoryConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.get("/v1/users/{user_id}/memory-audit", response_model=MemoryAuditCollection)
def read_memory_audit(
    user_id: UUID,
    limit: int = 100,
    store: SqlAlchemyStore = Depends(get_store),
) -> MemoryAuditCollection:
    try:
        store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    safe_limit = max(1, min(limit, 500))
    return MemoryAuditCollection(user_id=user_id, events=store.list_memory_audit(user_id, limit=safe_limit))


@app.post("/v1/analyses", response_model=AnalysisResult)
def analyse_opportunity(
    request: AnalysisRequest,
    service: AnalyseOpportunityService = Depends(get_analysis_service),
) -> AnalysisResult:
    """Backward-compatible stateless analysis endpoint."""
    return _execute_analysis(service, request)


@app.post("/v1/users/{user_id}/analyses", response_model=AnalysisResult)
def analyse_persisted_opportunity(
    user_id: UUID,
    request: PersistedAnalysisRequest,
    service: AnalyseOpportunityService = Depends(get_analysis_service),
    store: SqlAlchemyStore = Depends(get_store),
) -> AnalysisResult:
    try:
        profile = store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc

    result = _execute_analysis(
        service,
        AnalysisRequest(profile=profile, opportunity=request.opportunity),
    )
    store.save_analysis(profile, request.opportunity, result)
    return result


@app.get("/v1/users/{user_id}/analyses/{analysis_id}", response_model=AnalysisResult)
def read_analysis(
    user_id: UUID,
    analysis_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> AnalysisResult:
    try:
        return store.get_analysis(user_id, analysis_id)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found") from exc


@app.post("/v1/feedback", response_model=FeedbackResponse)
def record_feedback(request: FeedbackRequest) -> FeedbackResponse:
    """Backward-compatible stateless feedback endpoint."""
    updated, changes = apply_feedback(
        request.profile,
        request.feedback,
        opportunity_type=request.opportunity_type,
        company_industry=request.company_industry,
    )
    return FeedbackResponse(updated_profile=updated, applied_updates=changes)


@app.post("/v1/users/{user_id}/feedback", response_model=FeedbackResponse)
def record_persisted_feedback(
    user_id: UUID,
    request: PersistedFeedbackRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> FeedbackResponse:
    try:
        profile = store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc

    opportunity_type_value = store.get_analysis_opportunity_type(user_id, request.feedback.analysis_id)
    opportunity_type = (
        OpportunityType(opportunity_type_value)
        if opportunity_type_value in OpportunityType._value2member_map_
        else None
    )
    updated, changes = apply_feedback(
        profile,
        request.feedback,
        opportunity_type=opportunity_type,
        company_industry=request.company_industry,
    )
    try:
        store.record_feedback(updated, request.feedback, changes)
        if request.feedback.action == FeedbackAction.PURSUE:
            store.update_opportunity_status(request.feedback.analysis_id, Decision.PURSUE)
        elif request.feedback.action in {FeedbackAction.REJECT, FeedbackAction.NOT_RELEVANT}:
            store.update_opportunity_status(request.feedback.analysis_id, Decision.REJECT)
    except AnalysisNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found") from exc
    return FeedbackResponse(updated_profile=updated, applied_updates=changes)


@app.get("/v1/users/{user_id}/activity", response_model=UserActivitySummary)
def read_user_activity(
    user_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> UserActivitySummary:
    try:
        store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    return UserActivitySummary(user_id=user_id, analysis_count=store.count_user_analyses(user_id))
