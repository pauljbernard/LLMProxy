"""Native proxy endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.dependencies import get_async_session, get_runtime_settings, get_session, require_api_token, require_operator_token, require_platform_listener
from app.config import Settings
from app.proxy.candidates import (
    approve_training_candidate,
    get_training_candidate,
    list_training_candidates,
    reject_training_candidate,
    summarize_candidate_interactions,
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

router = APIRouter(prefix="/proxy", tags=["proxy-native"], dependencies=[Depends(require_platform_listener)])


@router.post("/ensemble", response_model=EnsembleResponse, dependencies=[Depends(require_api_token)])
async def ensemble(
    request: ChatCompletionRequest,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_runtime_settings),
) -> EnsembleResponse:
    request = request.model_copy(update={"model": "proxy-ensemble"})
    classification = classify_request(request)
    def _prepare(sync_session):
        request_log = record_request(sync_session, request, classification)
        sync_session.flush()
        selected_route = select_route(request_log.id, request, classification, settings, session=sync_session)
        selected_route.decision.selected_mode = "frontier_ensemble"
        record_routing_decision(sync_session, request_log.id, selected_route.decision)
        sync_session.flush()
        return request_log.id, selected_route

    request_log_id, selected_route = await session.run_sync(_prepare)
    response = await run_teacher_ensemble(
        request=request,
        request_log_id=request_log_id,
        routing_decision_id=selected_route.decision.routing_decision_id,
        session=session,
        settings=settings,
    )
    await session.commit()
    return response


@router.get("/training-candidates", dependencies=[Depends(require_api_token)])
def list_training_candidates_endpoint(
    paginated: bool = False,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    domain: str | None = Query(default=None),
    approval_status: str | None = Query(default=None),
    interaction_protocol: str | None = Query(default=None),
    interaction_operation: str | None = Query(default=None),
    interaction_outcome: str | None = Query(default=None),
    prompt_template_name: str | None = Query(default=None),
    prompt_template_version: int | None = None,
    prompt_template_selection_mode: str | None = Query(default=None, pattern="^(active|challenger_canary|explicit)$"),
    session: Session = Depends(get_session),
) -> list[TrainingCandidateView] | dict[str, Any]:
    candidates = list_training_candidates(
        session,
        domain=domain,
        approval_status=approval_status,
        interaction_protocol=interaction_protocol,
        interaction_operation=interaction_operation,
        interaction_outcome=interaction_outcome,
        prompt_template_name=prompt_template_name,
        prompt_template_version=prompt_template_version,
        prompt_template_selection_mode=prompt_template_selection_mode,
    )
    payload = [
        TrainingCandidateView.model_validate(
            {
                "id": candidate.id,
                "request_log_id": candidate.request_log_id,
                "routing_decision_id": candidate.routing_decision_id,
                "session_id": candidate.session_id,
                "domain": candidate.domain,
                "task_type": candidate.task_type,
                "status": candidate.status,
                "quality_score": candidate.quality_score,
                "approval_status": candidate.approval_status,
                "export_eligible": candidate.export_eligible,
                "selected_response": candidate.selected_response,
                "metadata": candidate.metadata_json,
                "requested_model": (candidate.metadata_json or {}).get("requested_model"),
                "effective_model": (candidate.metadata_json or {}).get("effective_model"),
                "prompt_template_name": (candidate.metadata_json or {}).get("prompt_template_name"),
                "prompt_template_version": (candidate.metadata_json or {}).get("prompt_template_version"),
                "prompt_template_render_hash": (candidate.metadata_json or {}).get("prompt_template_render_hash"),
                "prompt_template_selection_mode": (candidate.metadata_json or {}).get("prompt_template_selection_mode"),
                "prompt_template_rollout_percentage": (candidate.metadata_json or {}).get("prompt_template_rollout_percentage"),
                **summarize_candidate_interactions(candidate),
            }
        )
        for candidate in candidates
    ]
    if not paginated:
        return payload
    items = payload[offset:offset + limit]
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": len(payload),
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/training-candidates/{candidate_id}/approve",
    response_model=CandidateStatusUpdateResponse,
    dependencies=[Depends(require_api_token)],
)
def approve_candidate(
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
def reject_candidate(
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
def export_training_candidates(
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
def register_model(
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
