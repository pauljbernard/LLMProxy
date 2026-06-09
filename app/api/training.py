"""Training endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token, require_platform_listener
from app.config import Settings
from app.db.models import DatasetVersion, TrainingRun
from app.schemas.training import TrainingPreflightResponse, TrainingRunRequest, TrainingRunResponse, TrainingRunView
from app.training.orchestrator import create_training_run, list_training_runs
from app.training.preflight import build_training_preflight

router = APIRouter(prefix="/training", tags=["training"], dependencies=[Depends(require_platform_listener)])


def _training_run_view(run: TrainingRun) -> TrainingRunView:
    return TrainingRunView(
        id=run.id,
        dataset_version_id=run.dataset_version_id,
        base_model=run.base_model,
        training_mode=run.training_mode,
        trainer_backend=str(run.training_config_json.get("trainer_backend", "custom")),
        status=run.status,
        artifact_path=run.artifact_path,
        metrics=run.metrics_json,
    )


@router.post("/runs", response_model=TrainingRunResponse, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_api_token)])
def submit_training_run(
    request: TrainingRunRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> TrainingRunResponse:
    try:
        response = create_training_run(session, request=request, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return response


@router.get("/runs", dependencies=[Depends(require_api_token)])
def list_training_runs_endpoint(
    paginated: bool = False,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    base_model: str | None = None,
    session: Session = Depends(get_session),
) -> list[TrainingRunView] | dict[str, Any]:
    if paginated:
        statement = select(TrainingRun)
        if status:
            statement = statement.where(TrainingRun.status == status)
        if base_model:
            statement = statement.where(TrainingRun.base_model == base_model)
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
        rows = list(
            session.execute(
                statement.order_by(TrainingRun.started_at.desc()).limit(limit).offset(offset)
            ).scalars()
        )
        return {
            "items": [_training_run_view(run).model_dump(mode="json") for run in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    runs = list_training_runs(session)
    return [_training_run_view(run) for run in runs]


@router.post("/preflight", response_model=TrainingPreflightResponse, dependencies=[Depends(require_api_token)])
def preflight_training_run(
    request: TrainingRunRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> TrainingPreflightResponse:
    dataset_version = session.get(DatasetVersion, request.dataset_version_id)
    if dataset_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset version '{request.dataset_version_id}' was not found.",
        )
    try:
        return build_training_preflight(dataset_version=dataset_version, request=request, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
