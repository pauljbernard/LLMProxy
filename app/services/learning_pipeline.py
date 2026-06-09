"""Learning-pipeline traffic attribution and summaries."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import AuthPrincipal
from app.db.models import ModelResponse, RequestLog, VirtualAPIKey
from app.services.request_routing_summary import enrich_request_summary_with_routing, latest_routing_decisions_by_request
from app.schemas.chat import ChatCompletionRequest


def learning_pipeline_scope_from_owner(owner_id: str | None) -> str | None:
    if not owner_id:
        return None
    if owner_id.startswith("train_"):
        return "training"
    if owner_id.startswith("eval_"):
        return "evaluation"
    return None


def principal_traffic_context(principal: AuthPrincipal) -> dict[str, str | None]:
    scope = learning_pipeline_scope_from_owner(principal.owner_id)
    if scope:
        origin = "learning_pipeline"
    elif principal.role == "operator":
        origin = "interactive"
    elif principal.role == "automation":
        origin = "automation"
    elif principal.key_id:
        origin = "api_client"
    else:
        origin = "interactive"
    return {
        "traffic_origin": origin,
        "automation_scope": scope,
        "automation_owner_id": principal.owner_id,
        "virtual_key_id": principal.key_id,
        "virtual_key_role": principal.role if principal.key_id else None,
    }


def enrich_request_for_principal(
    request: ChatCompletionRequest,
    principal: AuthPrincipal,
) -> ChatCompletionRequest:
    context = principal_traffic_context(principal)
    enriched = request.model_copy(deep=True)
    enriched.metadata.traffic_origin = context["traffic_origin"]
    enriched.metadata.automation_scope = context["automation_scope"]
    enriched.metadata.automation_owner_id = context["automation_owner_id"]
    enriched.metadata.virtual_key_id = context["virtual_key_id"]
    enriched.metadata.virtual_key_role = context["virtual_key_role"]
    return enriched


def request_metadata_payload(request: RequestLog | dict[str, Any]) -> dict[str, Any]:
    if isinstance(request, RequestLog):
        payload = request.request_json or {}
    else:
        payload = request
    metadata = payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def request_traffic_origin(request: RequestLog | dict[str, Any]) -> str:
    metadata = request_metadata_payload(request)
    return str(metadata.get("traffic_origin") or "interactive")


def request_automation_scope(request: RequestLog | dict[str, Any]) -> str | None:
    metadata = request_metadata_payload(request)
    value = metadata.get("automation_scope")
    return str(value) if value else None


def request_automation_owner_id(request: RequestLog | dict[str, Any]) -> str | None:
    metadata = request_metadata_payload(request)
    value = metadata.get("automation_owner_id")
    return str(value) if value else None


def request_virtual_key_id(request: RequestLog | dict[str, Any]) -> str | None:
    metadata = request_metadata_payload(request)
    value = metadata.get("virtual_key_id")
    return str(value) if value else None


def request_virtual_key_role(request: RequestLog | dict[str, Any]) -> str | None:
    metadata = request_metadata_payload(request)
    value = metadata.get("virtual_key_role")
    return str(value) if value else None


def is_learning_pipeline_request(request: RequestLog | dict[str, Any]) -> bool:
    return request_traffic_origin(request) == "learning_pipeline"


def learning_pipeline_request_summary_payload(request: RequestLog) -> dict[str, Any]:
    metadata = request.request_json.get("metadata", {}) if isinstance(request.request_json, dict) else {}
    effective_request = request.effective_request_json if isinstance(request.effective_request_json, dict) else {}
    effective_metadata = effective_request.get("metadata") if isinstance(effective_request.get("metadata"), dict) else {}
    return {
        "id": request.id,
        "session_id": request.session_id,
        "requested_model": request.requested_model,
        "effective_model": effective_request.get("model"),
        "domain": request.domain,
        "task_type": request.task_type,
        "complexity": request.complexity,
        "privacy_level": request.privacy_level,
        "traffic_origin": request_traffic_origin(request),
        "automation_scope": request_automation_scope(request),
        "automation_owner_id": request_automation_owner_id(request),
        "virtual_key_id": request_virtual_key_id(request),
        "virtual_key_role": request_virtual_key_role(request),
        "prompt_template_name": metadata.get("prompt_template_name"),
        "prompt_template_version": metadata.get("prompt_template_version"),
        "prompt_template_render_hash": effective_metadata.get("prompt_template_render_hash"),
        "created_at": request.created_at,
    }


def learning_pipeline_spend_summary(session: Session) -> dict[str, float | int]:
    rows = list(session.execute(select(VirtualAPIKey)).scalars())
    training_spend = sum(float(item.spend_usd or 0) for item in rows if learning_pipeline_scope_from_owner(item.owner_id) == "training")
    evaluation_spend = sum(
        float(item.spend_usd or 0) for item in rows if learning_pipeline_scope_from_owner(item.owner_id) == "evaluation"
    )
    return {
        "training_pipeline_spend_usd": round(training_spend, 6),
        "evaluation_pipeline_spend_usd": round(evaluation_spend, 6),
        "learning_pipeline_spend_usd": round(training_spend + evaluation_spend, 6),
        "training_virtual_key_count": sum(1 for item in rows if learning_pipeline_scope_from_owner(item.owner_id) == "training"),
        "evaluation_virtual_key_count": sum(1 for item in rows if learning_pipeline_scope_from_owner(item.owner_id) == "evaluation"),
    }


def build_learning_pipeline_traffic_summary(session: Session, *, owner_id: str) -> dict[str, Any]:
    virtual_keys = list(
        session.execute(
            select(VirtualAPIKey).where(VirtualAPIKey.owner_id == owner_id).order_by(VirtualAPIKey.created_at.desc())
        ).scalars()
    )
    request_rows = [
        row
        for row in session.execute(select(RequestLog).order_by(RequestLog.created_at.desc())).scalars()
        if request_automation_owner_id(row) == owner_id
    ]
    request_ids = {row.id for row in request_rows}
    response_rows = [
        row
        for row in session.execute(select(ModelResponse).order_by(ModelResponse.created_at.desc())).scalars()
        if row.request_log_id in request_ids
    ]
    recent_requests = request_rows[:5]
    latest_routing = latest_routing_decisions_by_request(session, [row.id for row in recent_requests])
    total_virtual_key_spend = sum(float(item.spend_usd or 0) for item in virtual_keys)
    total_response_cost = sum(float(item.cost_estimate or 0) for item in response_rows)
    total_input_tokens = sum(int(item.input_tokens or 0) for item in response_rows)
    total_output_tokens = sum(int(item.output_tokens or 0) for item in response_rows)
    return {
        "owner_id": owner_id,
        "scope": learning_pipeline_scope_from_owner(owner_id) or "automation",
        "traffic_origin": "learning_pipeline",
        "request_count": len(request_rows),
        "response_count": len(response_rows),
        "virtual_key_count": len(virtual_keys),
        "total_virtual_key_spend_usd": round(total_virtual_key_spend, 6),
        "total_response_cost_usd": round(total_response_cost, 6),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "response_cost_gap_usd": round(total_virtual_key_spend - total_response_cost, 6),
        "last_request_at": request_rows[0].created_at if request_rows else None,
        "virtual_keys": [
            {
                "id": item.id,
                "key_prefix": item.key_prefix,
                "status": item.status,
                "role": item.role,
                "spend_usd": float(item.spend_usd or Decimal("0")),
                "last_used_at": item.last_used_at,
                "created_at": item.created_at,
            }
            for item in virtual_keys
        ],
        "recent_requests": [
            enrich_request_summary_with_routing(
                learning_pipeline_request_summary_payload(item),
                latest_routing.get(item.id),
            )
            for item in recent_requests
        ],
    }
