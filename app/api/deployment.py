"""Deployment endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token, require_operator_token
from app.config import Settings
from app.deployment.manager import deploy_model, list_routing_policies, rollback_model
from app.schemas.integration import DeploymentRequest, DeploymentResponse, RoutingPolicyVersionView
from app.services.observability import log_record

router = APIRouter(prefix="/deployment", tags=["deployment"])


@router.post(
    "/models/{model_alias}/activate",
    response_model=DeploymentResponse,
    dependencies=[Depends(require_operator_token)],
)
async def activate_model(
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
async def rollback(
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
    "/routing-policies",
    response_model=list[RoutingPolicyVersionView],
    dependencies=[Depends(require_api_token)],
)
async def list_routing_policy_versions(
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
