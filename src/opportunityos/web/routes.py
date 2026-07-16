from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse

from opportunityos.api.dependencies import get_store
from opportunityos.evaluation.correction import EvaluationCorrectionError, correct_evaluation_dataset
from opportunityos.evaluation.models import (
    CorrectEvaluationDatasetRequest,
    EvaluationDataset,
    EvaluationDatasetCollection,
    ExtendEvaluationDatasetRequest,
    MergeEvaluationDatasetsRequest,
)
from opportunityos.infrastructure.database import (
    EvaluationDatasetEmptyError,
    EvaluationDatasetNotFoundError,
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
    "/v1/users/{user_id}/evaluation-datasets/latest",
    response_model=EvaluationDatasetCollection,
)
def list_latest_evaluation_datasets(
    user_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationDatasetCollection:
    try:
        store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    return EvaluationDatasetCollection(
        user_id=user_id,
        datasets=store.list_evaluation_datasets(user_id, include_history=False),
    )


@router.get(
    "/v1/users/{user_id}/evaluation-datasets/history",
    response_model=EvaluationDatasetCollection,
)
def list_evaluation_dataset_history(
    user_id: UUID,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationDatasetCollection:
    try:
        store.get_profile(user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    return EvaluationDatasetCollection(
        user_id=user_id,
        datasets=store.list_evaluation_datasets(user_id, include_history=True),
    )


@router.post(
    "/v1/users/{user_id}/evaluation-datasets/merge",
    response_model=EvaluationDataset,
    status_code=status.HTTP_201_CREATED,
)
def merge_evaluation_datasets(
    user_id: UUID,
    request: MergeEvaluationDatasetsRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationDataset:
    try:
        return store.merge_evaluation_datasets(user_id, request.source_dataset_ids)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except EvaluationDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation dataset not found") from exc
    except EvaluationDatasetEmptyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/v1/users/{user_id}/evaluation-datasets/{dataset_id}/extend",
    response_model=EvaluationDataset,
    status_code=status.HTTP_201_CREATED,
)
def extend_evaluation_dataset(
    user_id: UUID,
    dataset_id: UUID,
    request: ExtendEvaluationDatasetRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationDataset:
    try:
        return store.extend_evaluation_dataset(user_id, dataset_id, request.extraction_labels)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except EvaluationDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation dataset not found") from exc
    except EvaluationDatasetEmptyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post(
    "/v1/users/{user_id}/evaluation-datasets/{dataset_id}/correct",
    response_model=EvaluationDataset,
    status_code=status.HTTP_201_CREATED,
)
def correct_frozen_evaluation_dataset(
    user_id: UUID,
    dataset_id: UUID,
    request: CorrectEvaluationDatasetRequest,
    store: SqlAlchemyStore = Depends(get_store),
) -> EvaluationDataset:
    try:
        return correct_evaluation_dataset(store, user_id, dataset_id, request)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found") from exc
    except EvaluationDatasetNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation dataset not found") from exc
    except EvaluationCorrectionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
