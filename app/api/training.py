"""Training endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token
from app.config import Settings
from app.schemas.training import TrainingRunRequest, TrainingRunResponse, TrainingRunView
from app.training.orchestrator import create_training_run, list_training_runs

router = APIRouter(prefix="/training", tags=["training"])


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


@router.get("/runs", response_model=list[TrainingRunView], dependencies=[Depends(require_api_token)])
def list_training_runs_endpoint(
    session: Session = Depends(get_session),
) -> list[TrainingRunView]:
    runs = list_training_runs(session)
    return [
        TrainingRunView(
            id=run.id,
            dataset_version_id=run.dataset_version_id,
            base_model=run.base_model,
            training_mode=run.training_mode,
            status=run.status,
            artifact_path=run.artifact_path,
            metrics=run.metrics_json,
        )
        for run in runs
    ]
