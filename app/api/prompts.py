"""Prompt template APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import AuthPrincipal, get_session, require_api_token, require_operator_token, require_proxy_listener
from app.services.prompt_templates import (
    compare_prompt_template_versions,
    diff_prompt_templates,
    evaluate_prompt_auto_promotion,
    normalize_prompt_auto_promotion_policy,
    promote_prompt_template_challenger,
    PromptTemplateCreateInput,
    PromptTemplateError,
    create_prompt_template,
    get_prompt_template,
    list_prompt_templates,
    normalize_prompt_rollout_mode,
    normalize_prompt_template_status,
    prompt_family_rollout_payload,
    prompt_template_payload,
    render_prompt_template,
    set_prompt_auto_promotion_policy,
    set_prompt_template_rollout,
    set_prompt_template_status,
)

router = APIRouter(tags=["prompts"], dependencies=[Depends(require_proxy_listener)])


class PromptTemplateCreateRequest(BaseModel):
    name: str
    template_text: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    model_override: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptTemplateRenderRequest(BaseModel):
    version: int | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptTemplateStatusUpdateRequest(BaseModel):
    status: str


class PromptTemplateRolloutUpdateRequest(BaseModel):
    challenger_version: int | None = None
    mode: str = "disabled"
    traffic_percentage: float | None = None


class PromptTemplateAutoPromotionPolicyRequest(BaseModel):
    enabled: bool = False
    minimum_challenger_requests: int = 10
    min_candidate_yield_improvement_pct: float = 2.0
    max_error_rate_regression_pct: float = 1.0
    max_latency_regression_ms: float = 250.0
    max_cost_regression_usd: float = 0.001


@router.get("/v1/prompts")
def list_prompts(
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> list[dict[str, Any]]:
    family_rollouts: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for item in list_prompt_templates(session):
        family_rollouts.setdefault(item.name, prompt_family_rollout_payload(session, name=item.name))
        payload = prompt_template_payload(item)
        payload["family_rollout"] = family_rollouts[item.name]
        rows.append(payload)
    return rows


@router.get("/v1/prompts/{name}")
def get_prompt(
    name: str,
    version: int | None = Query(default=None),
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> dict[str, Any]:
    record = get_prompt_template(session, name=name, version=version)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found.")
    payload = prompt_template_payload(record)
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    return payload


@router.post("/v1/prompts/{name}/render")
def render_prompt(
    name: str,
    request: PromptTemplateRenderRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> dict[str, Any]:
    try:
        record, rendered = render_prompt_template(
            session,
            name=name,
            version=request.version,
            variables=request.variables,
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    payload = prompt_template_payload(record)
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    payload["rendered_text"] = rendered
    payload["render_variables"] = request.variables
    return payload


@router.get("/v1/prompts/{name}/diff")
def diff_prompt(
    name: str,
    from_version: int,
    to_version: int,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> dict[str, Any]:
    try:
        return diff_prompt_templates(session, name=name, from_version=from_version, to_version=to_version)
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/v1/prompts/{name}/comparison")
def compare_prompt(
    name: str,
    baseline_version: int | None = Query(default=None),
    compare_version: int | None = Query(default=None),
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> dict[str, Any]:
    try:
        return compare_prompt_template_versions(
            session,
            name=name,
            baseline_version=baseline_version,
            compare_version=compare_version,
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/v1/prompts", status_code=status.HTTP_201_CREATED)
def create_prompt(
    request: PromptTemplateCreateRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    record = create_prompt_template(
        session,
        PromptTemplateCreateInput(
            name=request.name,
            template_text=request.template_text,
            description=request.description,
            variables=request.variables,
            model_override=request.model_override,
            status=request.status,
            metadata=request.metadata,
        ),
    )
    payload = prompt_template_payload(record)
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    return payload


@router.post("/v1/prompts/{name}/{version}/status")
def update_prompt_status(
    name: str,
    version: int,
    request: PromptTemplateStatusUpdateRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    try:
        record = set_prompt_template_status(
            session,
            name=name,
            version=version,
            status=normalize_prompt_template_status(request.status),
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    payload = prompt_template_payload(record)
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    return payload


@router.post("/v1/prompts/{name}/rollout")
def update_prompt_rollout(
    name: str,
    request: PromptTemplateRolloutUpdateRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    try:
        return set_prompt_template_rollout(
            session,
            name=name,
            challenger_version=request.challenger_version,
            mode=normalize_prompt_rollout_mode(request.mode),
            traffic_percentage=request.traffic_percentage,
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/v1/prompts/{name}/promote-challenger")
def promote_prompt_challenger(
    name: str,
    challenger_version: int | None = Query(default=None),
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    try:
        return promote_prompt_template_challenger(
            session,
            name=name,
            challenger_version=challenger_version,
            guarded=True,
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/v1/prompts/{name}/auto-promotion-policy")
def update_prompt_auto_promotion_policy(
    name: str,
    request: PromptTemplateAutoPromotionPolicyRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    try:
        return set_prompt_auto_promotion_policy(
            session,
            name=name,
            enabled=request.enabled,
            minimum_challenger_requests=request.minimum_challenger_requests,
            min_candidate_yield_improvement_pct=request.min_candidate_yield_improvement_pct,
            max_error_rate_regression_pct=request.max_error_rate_regression_pct,
            max_latency_regression_ms=request.max_latency_regression_ms,
            max_cost_regression_usd=request.max_cost_regression_usd,
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/v1/prompts/{name}/auto-promotion/evaluate")
def evaluate_prompt_auto_promotion_api(
    name: str,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    try:
        return evaluate_prompt_auto_promotion(session, name=name)
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
