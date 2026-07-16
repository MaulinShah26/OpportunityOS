from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from opportunityos.api.dependencies import get_store
from opportunityos.evaluation.models import (
    CreateEvaluationDatasetRequest,
    EvaluationCandidateCollection,
    EvaluationDataset,
)
from opportunityos.infrastructure.database import (
    EvaluationDatasetEmptyError,
    ProfileNotFoundError,
    SqlAlchemyStore,
)

WEB_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = WEB_ROOT / "static"

router = APIRouter(include_in_schema=False)


@router.get("/")
def root() -> RedirectResponse:
    return RedirectResponse(url="/app", status_code=307)


@router.get("/app")
@router.get("/app/")
def application_shell() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html", media_type="text/html")


@router.get(
    "/v1/users/{user_id}/evaluation-candidates",
    response_model=EvaluationCandidateCollection,
)
def list_evaluation_candidates(
    user_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationCandidateCollection:
    try:
        candidates = store.list_evaluation_candidates(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    return EvaluationCandidateCollection(user_id=user_id, candidates=candidates)


@router.post(
    "/v1/users/{user_id}/evaluation-datasets-labelled",
    response_model=EvaluationDataset,
    status_code=status.HTTP_201_CREATED,
)
def create_extraction_labelled_dataset(
    user_id: UUID,
    request: CreateEvaluationDatasetRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationDataset:
    try:
        return store.create_evaluation_dataset(
            user_id,
            request.name,
            extraction_labels=request.extraction_labels,
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except EvaluationDatasetEmptyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
