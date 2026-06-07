"""Prompt template APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import AuthPrincipal, get_session, require_api_token, require_operator_token
from app.services.prompt_templates import (
    diff_prompt_templates,
    PromptTemplateCreateInput,
    PromptTemplateError,
    create_prompt_template,
    get_prompt_template,
    list_prompt_templates,
    prompt_template_payload,
    render_prompt_template,
)

router = APIRouter(tags=["prompts"])


class PromptTemplateCreateRequest(BaseModel):
    name: str
    template_text: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    model_override: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptTemplateRenderRequest(BaseModel):
    version: int | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


@router.get("/v1/prompts")
def list_prompts(
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> list[dict[str, Any]]:
    return [prompt_template_payload(item) for item in list_prompt_templates(session)]


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
    return prompt_template_payload(record)


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
            metadata=request.metadata,
        ),
    )
    return prompt_template_payload(record)
