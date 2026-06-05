"""Native proxy endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token, require_operator_token
from app.config import Settings
from app.proxy.candidates import (
    approve_training_candidate,
    get_training_candidate,
    list_training_candidates,
    reject_training_candidate,
)
from app.proxy.classifier import classify_request
from app.proxy.ensemble import run_teacher_ensemble
from app.proxy.exporter import export_candidates
from app.proxy.recorder import record_request, record_routing_decision
from app.proxy.router import select_route
from app.registry.artifact_store import register_model_package
from app.schemas.candidate import (
    CandidateStatusUpdateResponse,
    DatasetExportRequest,
    DatasetExportResponse,
    TrainingCandidateView,
)
from app.schemas.chat import ChatCompletionRequest
from app.schemas.ensemble import EnsembleResponse
from app.schemas.registry import ModelRegistrationRequest, ModelRegistrationResponse

router = APIRouter(prefix="/proxy", tags=["proxy-native"])


@router.post("/ensemble", response_model=EnsembleResponse, dependencies=[Depends(require_api_token)])
async def ensemble(
    request: ChatCompletionRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> EnsembleResponse:
    request = request.model_copy(update={"model": "proxy-ensemble"})
    classification = classify_request(request)
    request_log = record_request(session, request, classification)
    session.flush()
    selected_route = select_route(request_log.id, request, classification, settings)
    selected_route.decision.selected_mode = "frontier_ensemble"
    record_routing_decision(session, request_log.id, selected_route.decision)
    session.flush()
    response = await run_teacher_ensemble(
        request=request,
        request_log_id=request_log.id,
        routing_decision_id=selected_route.decision.routing_decision_id,
        session=session,
        settings=settings,
    )
    session.commit()
    return response


@router.get("/training-candidates", response_model=list[TrainingCandidateView], dependencies=[Depends(require_api_token)])
async def list_training_candidates_endpoint(
    session: Session = Depends(get_session),
) -> list[TrainingCandidateView]:
    candidates = list_training_candidates(session)
    return [
        TrainingCandidateView(
            id=candidate.id,
            request_log_id=candidate.request_log_id,
            routing_decision_id=candidate.routing_decision_id,
            session_id=candidate.session_id,
            domain=candidate.domain,
            task_type=candidate.task_type,
            status=candidate.status,
            quality_score=candidate.quality_score,
            approval_status=candidate.approval_status,
            export_eligible=candidate.export_eligible,
            selected_response=candidate.selected_response,
            metadata=candidate.metadata_json,
        )
        for candidate in candidates
    ]


@router.post(
    "/training-candidates/{candidate_id}/approve",
    response_model=CandidateStatusUpdateResponse,
    dependencies=[Depends(require_api_token)],
)
async def approve_candidate(
    candidate_id: str,
    session: Session = Depends(get_session),
) -> CandidateStatusUpdateResponse:
    candidate = get_training_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training candidate not found.")
    approve_training_candidate(session, candidate)
    session.commit()
    return CandidateStatusUpdateResponse(
        candidate_id=candidate.id,
        status=candidate.status,
        approval_status=candidate.approval_status,
        export_eligible=candidate.export_eligible,
    )


@router.post(
    "/training-candidates/{candidate_id}/reject",
    response_model=CandidateStatusUpdateResponse,
    dependencies=[Depends(require_api_token)],
)
async def reject_candidate(
    candidate_id: str,
    session: Session = Depends(get_session),
) -> CandidateStatusUpdateResponse:
    candidate = get_training_candidate(session, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training candidate not found.")
    reject_training_candidate(session, candidate)
    session.commit()
    return CandidateStatusUpdateResponse(
        candidate_id=candidate.id,
        status=candidate.status,
        approval_status=candidate.approval_status,
        export_eligible=candidate.export_eligible,
    )


@router.post("/export/jsonl", response_model=DatasetExportResponse, dependencies=[Depends(require_api_token)])
async def export_training_candidates(
    request: DatasetExportRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> DatasetExportResponse:
    try:
        response = export_candidates(session, request=request, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return response


@router.post("/models/register", response_model=ModelRegistrationResponse, dependencies=[Depends(require_operator_token)])
async def register_model(
    request: ModelRegistrationRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> ModelRegistrationResponse:
    manifest, manifest_path = register_model_package(
        Path(settings.llmproxy_models_path),
        request.model_dump(mode="json"),
    )
    return ModelRegistrationResponse(
        model_registry_id=str(manifest["model_registry_id"]),
        model_alias=str(manifest["model_alias"]),
        manifest_path=manifest_path,
        status=str(manifest["status"]),
        runtime=str(manifest["runtime"]),
    )
