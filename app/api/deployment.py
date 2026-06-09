"""Deployment endpoints."""

from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token, require_operator_token, require_platform_listener
from app.config import Settings
from app.deployment.manager import delete_policy_entry, deploy_model, list_local_deployment_inventory, list_routing_policies, rollback_model, upsert_frontier_policy_entry
from app.schemas.integration import (
    DeploymentRequest,
    DeploymentResponse,
    FrontierPolicyEntryRequest,
    RoutingPolicyEntryMutationResponse,
    RoutingPolicyVersionView,
)
from app.services.ollama_runtime import pull_ollama_model, reconcile_ollama_runtime
from app.services.observability import log_record

router = APIRouter(prefix="/deployment", tags=["deployment"], dependencies=[Depends(require_platform_listener)])


class OllamaPullRequest(BaseModel):
    model: str


@router.post(
    "/models/{model_alias}/activate",
    response_model=DeploymentResponse,
    dependencies=[Depends(require_operator_token)],
)
def activate_model(
    model_alias: str,
    request: DeploymentRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> DeploymentResponse:
    try:
        response = deploy_model(session, model_alias=model_alias, request=request, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    log_record(
        settings,
        level="INFO",
        component="deployment",
        category="audit",
        message="Model activated",
        data={"model_alias": model_alias, "deployment_mode": request.deployment_mode, "domains": request.domains, "task_types": request.task_types},
        audit=True,
    )
    return response


@router.post(
    "/models/{model_alias}/rollback",
    response_model=DeploymentResponse,
    dependencies=[Depends(require_operator_token)],
)
def rollback(
    model_alias: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> DeploymentResponse:
    try:
        response = rollback_model(session, model_alias=model_alias, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    log_record(
        settings,
        level="INFO",
        component="deployment",
        category="audit",
        message="Model rolled back",
        data={"model_alias": model_alias},
        audit=True,
    )
    return response


@router.get(
    "/models/local-inventory",
    dependencies=[Depends(require_api_token)],
)
def list_local_deployments(
    paginated: bool = False,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, object]] | dict[str, Any]:
    rows = list_local_deployment_inventory(session, settings=settings)
    if not paginated:
        return rows
    return {
        "items": rows[offset:offset + limit],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/runtimes/ollama/reconcile",
    dependencies=[Depends(require_api_token)],
)
def reconcile_ollama(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, object]:
    try:
        return reconcile_ollama_runtime(session, settings=settings)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post(
    "/runtimes/ollama/pull",
    dependencies=[Depends(require_operator_token)],
)
def pull_ollama(
    request: OllamaPullRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, object]:
    try:
        response = pull_ollama_model(settings=settings, model_name=request.model)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    log_record(
        settings,
        level="INFO",
        component="deployment",
        category="audit",
        message="Ollama model pull requested",
        data={"model": request.model},
        audit=True,
    )
    return response


@router.get(
    "/routing-policies",
    response_model=list[RoutingPolicyVersionView],
    dependencies=[Depends(require_api_token)],
)
def list_routing_policy_versions(
    session: Session = Depends(get_session),
) -> list[RoutingPolicyVersionView]:
    return [
        RoutingPolicyVersionView(
            id=policy.id,
            policy_version=policy.policy_version,
            policy=policy.policy_json,
        )
        for policy in list_routing_policies(session)
    ]


@router.post(
    "/routing-policies/frontier",
    response_model=RoutingPolicyEntryMutationResponse,
    dependencies=[Depends(require_operator_token)],
)
def upsert_frontier_policy(
    request: FrontierPolicyEntryRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> RoutingPolicyEntryMutationResponse:
    entry_id, policy_version = upsert_frontier_policy_entry(session, request=request)
    session.commit()
    log_record(
        settings,
        level="INFO",
        component="deployment",
        category="audit",
        message="Frontier routing policy entry upserted",
        data={
            "entry_id": entry_id,
            "provider_key": request.provider_key,
            "domains": request.domains,
            "deployment_mode": request.deployment_mode,
        },
        audit=True,
    )
    return RoutingPolicyEntryMutationResponse(
        entry_id=entry_id,
        policy_version=policy_version,
        action="updated" if request.entry_id else "created",
    )


@router.delete(
    "/routing-policies/entries/{entry_id}",
    response_model=RoutingPolicyEntryMutationResponse,
    dependencies=[Depends(require_operator_token)],
)
def remove_routing_policy_entry(
    entry_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> RoutingPolicyEntryMutationResponse:
    try:
        policy_version = delete_policy_entry(session, entry_id=entry_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    session.commit()
    log_record(
        settings,
        level="INFO",
        component="deployment",
        category="audit",
        message="Routing policy entry deleted",
        data={"entry_id": entry_id, "policy_version": policy_version},
        audit=True,
    )
    return RoutingPolicyEntryMutationResponse(
        entry_id=entry_id,
        policy_version=policy_version,
        action="deleted",
    )
