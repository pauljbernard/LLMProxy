"""Administrative operator UI and API."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from time import perf_counter

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.dependencies import (
    AuthPrincipal,
    get_runtime_settings,
    get_session,
    require_admin_listener,
    virtual_key_hash,
    require_api_token,
    require_operator_token,
)
from app.api.virtual_keys import (
    VirtualKeyCreateRequest,
    VirtualKeyCreateResponse,
    VirtualKeyRotateResponse,
    VirtualKeyUpdateRequest,
    VirtualKeyView,
    create_virtual_key_record,
    disable_virtual_key_record,
    list_virtual_key_records,
    rotate_virtual_key_record,
    update_virtual_key_record,
    virtual_key_payload,
)
from app.config import Settings, get_settings
from app.db.models import DatasetExport, DatasetImport, DatasetVersion, EvaluationRun, IntegrationEvent, JobQueueRecord, JudgeCritique, ModelPerformanceSample, ModelResponse, PromptTemplate, RequestLog, RoutingDecisionRecord, TrainingCandidate, TrainingRun
from app.db.session import get_session_factory
from app.integration.events import emit_event
from app.integration.outbox import process_pending_events
from app.integration.jobs import enqueue_replicate_prediction_job
from app.operator_payloads import (
    dataset_export_payload,
    dataset_import_payload,
    dataset_version_payload,
    evaluation_run_payload,
    event_payload,
    job_payload,
    model_response_payload,
    request_detail_payload,
    request_summary_payload,
    routing_decision_payload,
    settings_payload,
    training_candidate_payload,
    training_run_payload,
)
from app.proxy.classifier import classify_request
from app.proxy.candidates import capture_training_candidate
from app.proxy.recorder import generate_prefixed_id
from app.proxy.router import select_route
from app.registry.model_registry import get_provider_registry, list_provider_capabilities, list_provider_capabilities_async, resolve_provider
from app.runtime import run_scheduler_iteration, run_worker_iteration
from app.services.cost import pricing_catalog
from app.services.learning_pipeline import build_learning_pipeline_traffic_summary
from app.services.local_runtime_status import build_local_runtime_status
from app.services.a2a_registry import inspect_a2a_peer, invoke_a2a_peer, list_a2a_peers
from app.services.mcp_gateway import _list_mcp_tools, inspect_mcp_server
from app.services.observability import build_operations_summary, log_record, tail_log_records
from app.services.rest_registry import inspect_rest_endpoint, invoke_rest_endpoint, list_rest_endpoints
from app.services.request_routing_summary import enrich_request_summary_with_routing, latest_routing_decisions_by_request
from app.services.routing_topology import build_routing_topology_inventory
from app.services.prompt_templates import (
    build_prompt_template_metrics,
    compare_prompt_template_versions,
    evaluate_prompt_auto_promotion,
    promote_prompt_template_challenger,
    PromptTemplateCreateInput,
    PromptTemplateError,
    create_prompt_template,
    diff_prompt_templates,
    get_prompt_template,
    list_prompt_templates,
    normalize_prompt_template_status,
    normalize_prompt_rollout_mode,
    prompt_family_rollout_payload,
    prompt_template_payload,
    render_prompt_template,
    set_prompt_auto_promotion_policy,
    set_prompt_template_rollout,
    set_prompt_template_status,
)
from app.services.model_monitoring import enqueue_due_model_monitor_jobs, list_model_monitors, run_model_monitor
from app.services.llm_timeseries import build_llm_timeseries
from app.services.replicate_predictions import run_replicate_prediction
from app.services.training_runtime import get_reported_training_runtime_status
from app.services.training_studio import get_training_studio_status
from app.schemas.chat import ChatCompletionRequest

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_listener)])

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static" / "admin"
OPS_EVENTS_SCAN_MULTIPLIER = 8
OPS_EVENTS_MIN_SCAN_LIMIT = 1000
OPS_EVENTS_MAX_SCAN_LIMIT = 20000
OPS_EVENTS_SECONDARY_MIN_SCAN_LIMIT = 250
OPS_EVENTS_SECONDARY_MAX_SCAN_LIMIT = 2000
OPS_EVENTS_HISTORY_SCAN_MULTIPLIER = 4
OPS_EVENTS_HISTORY_MAX_SCAN_LIMIT = 100000
OPS_EVENTS_SECONDARY_HISTORY_MAX_SCAN_LIMIT = 10000
OPS_EVENTS_ACTIVE_WINDOW_HOURS = 24
STREAMING_VALIDATION_SUITE_CACHE: dict[str, dict[str, Any]] = {}


def _ops_event_class(record: dict[str, Any]) -> str:
    if bool(record.get("audit")):
        return "audit"
    if str(record.get("level") or "").upper() in {"ERROR", "CRITICAL"}:
        return "error"
    return "log"


def build_ops_record_key(record: dict[str, Any]) -> str:
    source_record_id = str(record.get("source_record_id") or "").strip()
    event_source = str(record.get("event_source") or "").strip()
    if source_record_id and event_source:
        return f"{event_source}:{source_record_id}"
    return "|".join(
        str(value or "")
        for value in [
            record.get("timestamp"),
            record.get("event_class") or _ops_event_class(record),
            record.get("level"),
            record.get("component"),
            record.get("message"),
        ]
    )


def _ops_event_sort_value(record: dict[str, Any], sort_by: str) -> Any:
    if sort_by == "event_class":
        return str(record.get("event_class") or _ops_event_class(record))
    if sort_by == "event_source":
        return str(record.get("event_source") or "").lower()
    if sort_by in {"requested_model", "selected_provider", "selected_model", "traffic_origin", "domain", "task_type"}:
        return str(record.get(sort_by) or "").lower()
    if sort_by in {"latency_ms", "first_response_latency_ms", "cost_estimate", "input_tokens", "output_tokens", "total_tokens"}:
        try:
            return float(record.get(sort_by) or 0)
        except (TypeError, ValueError):
            return 0.0
    if sort_by in {"level", "component", "category", "message"}:
        return str(record.get(sort_by) or "").lower()
    if sort_by == "listener_id":
        data = record.get("data") or {}
        if not isinstance(data, dict):
            data = {}
        nested_metadata = data.get("metadata") or {}
        if not isinstance(nested_metadata, dict):
            nested_metadata = {}
        return str(data.get("listener_id") or nested_metadata.get("listener_id") or "").lower()
    return str(record.get("timestamp") or "")


def _operational_event_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = dict(record)
    payload["event_class"] = _ops_event_class(record)
    payload["event_source"] = "ops_log"
    payload["training_opportunity"] = True
    payload["promotable"] = True
    payload["source_record_id"] = build_ops_record_key(record)
    return payload


def _job_operational_event_payload(job: JobQueueRecord) -> dict[str, Any]:
    payload = job_payload(job)
    listener_id = str((payload.get("payload") or {}).get("listener_id") or "").strip() or None
    return {
        "timestamp": payload.get("created_at"),
        "level": "ERROR" if str(payload.get("status") or "").lower() == "failed" else "INFO",
        "component": "runtime.jobs",
        "category": "job",
        "message": f"Job {payload.get('job_type') or 'unknown'} is {payload.get('status') or 'pending'}",
        "data": payload,
        "event_class": "job",
        "event_source": "job",
        "training_opportunity": True,
        "promotable": True,
        "source_record_id": payload.get("id"),
        "listener_id": listener_id,
    }


def _runtime_event_operational_event_payload(event: IntegrationEvent) -> dict[str, Any]:
    payload = event_payload(event)
    raw_payload = payload.get("payload_json") or {}
    listener_id = str(raw_payload.get("listener_id") or raw_payload.get("metadata", {}).get("listener_id") or "").strip() or None
    return {
        "timestamp": payload.get("occurred_at"),
        "level": "INFO",
        "component": f"runtime.events.{payload.get('source') or 'integration'}",
        "category": "runtime_event",
        "message": f"{payload.get('event_type') or 'event'} from {payload.get('source') or 'runtime'}",
        "data": payload,
        "event_class": "runtime_event",
        "event_source": "runtime_event",
        "training_opportunity": True,
        "promotable": True,
        "source_record_id": payload.get("id"),
        "listener_id": listener_id,
    }


def _request_operational_event_payload(summary: dict[str, Any]) -> dict[str, Any]:
    requested_model = str(summary.get("requested_model") or "").strip() or "unknown"
    selected_provider = str(summary.get("selected_provider") or "").strip()
    selected_model = str(summary.get("selected_model") or "").strip()
    selected_mode = str(summary.get("selected_mode") or "").strip()
    route_target = selected_model or requested_model
    route_label = f"{selected_provider}/{route_target}" if selected_provider else route_target
    message = f"Request {requested_model} -> {route_label}"
    if selected_mode:
        message = f"{message} ({selected_mode})"
    raw_cost_estimate = summary.get("cost_estimate")
    try:
        cost_estimate = float(raw_cost_estimate) if raw_cost_estimate is not None else None
    except (TypeError, ValueError):
        cost_estimate = None
    return {
        "timestamp": summary.get("created_at"),
        "level": "INFO" if selected_provider else "ERROR",
        "component": "proxy.request",
        "category": "traffic",
        "message": message,
        "data": summary,
        "event_class": "request",
        "event_source": "request",
        "training_opportunity": True,
        "promotable": True,
        "source_record_id": summary.get("id"),
        "listener_id": summary.get("listener_id"),
        "requested_model": summary.get("requested_model"),
        "selected_provider": summary.get("selected_provider"),
        "selected_model": summary.get("selected_model"),
        "selected_pool_id": summary.get("selected_pool_id"),
        "selected_node_id": summary.get("selected_node_id"),
        "traffic_origin": summary.get("traffic_origin"),
        "automation_scope": summary.get("automation_scope"),
        "domain": summary.get("domain"),
        "task_type": summary.get("task_type"),
        "prompt_template_name": summary.get("prompt_template_name"),
        "prompt_template_version": summary.get("prompt_template_version"),
        "prompt_template_render_hash": summary.get("prompt_template_render_hash"),
        "prompt_template_selection_mode": summary.get("prompt_template_selection_mode"),
        "prompt_template_rollout_percentage": summary.get("prompt_template_rollout_percentage"),
        "latency_ms": summary.get("latency_ms"),
        "first_response_latency_ms": summary.get("first_response_latency_ms"),
        "cost_estimate": cost_estimate,
        "input_tokens": summary.get("input_tokens"),
        "output_tokens": summary.get("output_tokens"),
        "total_tokens": summary.get("total_tokens"),
    }


def _latest_selected_responses_by_request(
    session: Session,
    request_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not request_ids:
        return {}
    rows = list(
        session.execute(
            select(ModelResponse)
            .where(
                ModelResponse.request_log_id.in_(request_ids),
                ModelResponse.response_role == "selected_response",
            )
            .order_by(ModelResponse.created_at.desc())
        ).scalars()
    )
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.request_log_id in latest:
            continue
        latest[row.request_log_id] = model_response_payload(row)
    return latest


def _promote_operational_event_to_candidate(
    session: Session,
    *,
    event: dict[str, Any],
    domain: str,
    task_type: str,
    approve_immediately: bool,
) -> TrainingCandidate:
    event_source = str(event.get("event_source") or "ops_log")
    event_class = str(event.get("event_class") or "log")
    session_id = str(event.get("listener_id") or generate_prefixed_id("sess"))
    request_log = RequestLog(
        id=generate_prefixed_id("req"),
        session_id=session_id,
        external_request_id=None,
        requested_model=f"observability:{event_source}",
        domain=domain,
        task_type=task_type,
        complexity="medium",
        privacy_level="standard",
        request_json={"event": event},
    )
    session.add(request_log)
    routing_decision = RoutingDecisionRecord(
        id=generate_prefixed_id("route"),
        request_log_id=request_log.id,
        session_id=session_id,
        policy_version="observability-promoted",
        selected_provider="internal:observability",
        selected_provider_family="llmProxy Observability",
        selected_model=f"{event_source}:{event_class}",
        selected_mode="event_capture",
        selected_entry_id=None,
        selected_pool_id=None,
        selected_node_id=None,
        selected_node_role=None,
        selected_node_labels_json=[],
        selected_capacity_class=None,
        selected_balancing_strategy=None,
        selected_affinity_key=None,
        decision_rationale="Promoted from the unified operational event directory.",
        predicted_cost_class="none",
        predicted_latency_class="none",
        ranked_alternatives_json=[],
        fallback_chain_json=[],
    )
    session.add(routing_decision)
    event_message = str(event.get("message") or "Operational event")
    event_payload = event.get("data") or {}
    candidate = capture_training_candidate(
        session,
        request_log_id=request_log.id,
        routing_decision_id=routing_decision.id,
        session_id=session_id,
        domain=domain,
        task_type=task_type,
        quality_score=None,
        selected_response=json.dumps(
            {
                "summary": event_message,
                "event_class": event_class,
                "event_source": event_source,
                "payload": event_payload,
            },
            sort_keys=True,
        ),
        messages=[
            {
                "role": "system",
                "content": "Operational event promoted from llmProxy observability for training/evaluation curation.",
            },
            {
                "role": "user",
                "content": json.dumps(event, sort_keys=True),
            },
        ],
        provenance={
            "promotion_source": "observability_event",
            "event_source": event_source,
            "event_class": event_class,
            "interaction_traces": [
                {
                    "protocol": "llmproxy_event",
                    "operation": "promote_event",
                    "success": True,
                    "metadata": {
                        "event_source": event_source,
                        "event_class": event_class,
                        "source_record_id": event.get("source_record_id"),
                    },
                }
            ],
            "event": event,
        },
        validation={"promoted_from_event": True},
        metadata={
            "event_source": event_source,
            "event_class": event_class,
            "training_opportunity": True,
            "source_record_id": event.get("source_record_id"),
        },
    )
    if approve_immediately:
        candidate.status = "approved"
        candidate.approval_status = "approved"
        candidate.export_eligible = True
    return candidate


class ConfigSetRequest(BaseModel):
    key: str
    value: str
    env_file: str = ".env.local"


class JobRetryRequest(BaseModel):
    reset_attempts: bool = False
    available_now: bool = False


class OperationalEventPromoteRequest(BaseModel):
    event: dict[str, Any]
    domain: str = "operations"
    task_type: str = "event_review"
    approve_immediately: bool = False


class StreamingValidationRequest(BaseModel):
    provider_key: str | None = None
    prompt: str = "Say hello briefly."
    requested_model: str = "proxy-auto"
    domain_hint: str = "general"
    task_type_hint: str = "analysis"
    max_chunks: int = 12
    listener_id: str | None = None
    execution_mode: Literal["interactive", "training", "evaluation"] = "training"
    owner_id: str | None = None
    validation_scope: Literal["default_only", "all_discovered"] = "default_only"
    target_filter: Literal["all_streamable", "chat_capable_subset"] = "all_streamable"
    max_concurrency: int = Field(default=6, ge=1, le=24)
    use_cached_results: bool = True
    cache_ttl_seconds: int = Field(default=900, ge=0, le=86400)


class ProviderValidationRequest(BaseModel):
    provider_key: str
    prompt: str = "Say hello briefly."


class ReplicatePredictionRequest(BaseModel):
    model: str
    input: dict[str, object]
    wait_for_completion: bool = True


class A2APeerInvokeRequest(BaseModel):
    capability: str
    input: dict[str, object] = Field(default_factory=dict)


class RestEndpointInvokeRequest(BaseModel):
    method: str | None = None
    path: str | None = None
    input: dict[str, object] = Field(default_factory=dict)


class RoutingSettingsUpdateRequest(BaseModel):
    routing_strategy: str
    frontier_default_entries: list[dict[str, object]]
    env_file: str = ".env.local"


class InboundListenerDefinitionRequest(BaseModel):
    listener_id: str
    name: str | None = None
    host: str = "0.0.0.0"
    port: int
    published_host: str | None = None
    published_port: int | None = None
    exposes_admin: bool = False
    exposes_platform_api: bool = False
    exposes_proxy: bool = True


class InboundListenerConfigUpdateRequest(BaseModel):
    listeners: list[InboundListenerDefinitionRequest]
    env_file: str = ".env.local"


class ModelMonitorDefinitionRequest(BaseModel):
    monitor_id: str | None = None
    label: str | None = None
    provider_key: str
    model_id: str
    enabled: bool = True
    frequency_minutes: int = Field(default=60, ge=5, le=10080)
    monitor_mode: Literal["frontdoor_stream", "provider_healthcheck"] = "frontdoor_stream"
    listener_id: str | None = None
    prompt: str | None = None


class ModelMonitorConfigUpdateRequest(BaseModel):
    monitors: list[ModelMonitorDefinitionRequest]
    env_file: str = ".env"


class PromptTemplateAdminCreateRequest(BaseModel):
    name: str
    template_text: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    model_override: str | None = None
    status: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class PromptTemplateAdminRenderRequest(BaseModel):
    version: int | None = None
    variables: dict[str, object] = Field(default_factory=dict)


class PromptTemplateAdminStatusUpdateRequest(BaseModel):
    status: str


class PromptTemplateAdminRolloutRequest(BaseModel):
    challenger_version: int | None = None
    mode: str = "disabled"
    traffic_percentage: float | None = None


class PromptTemplateAdminAutoPromotionPolicyRequest(BaseModel):
    enabled: bool = False
    minimum_challenger_requests: int = 10
    min_candidate_yield_improvement_pct: float = 2.0
    max_error_rate_regression_pct: float = 1.0
    max_latency_regression_ms: float = 250.0
    max_cost_regression_usd: float = 0.001


class RoutePreviewRequest(BaseModel):
    model: str = "proxy-auto"
    temperature: float = 0.2
    max_tokens: int = 1024
    messages: list[dict[str, object]]
    session_id: str
    listener_id: str | None = None
    domain_hint: str | None = None
    task_type_hint: str | None = None
    region_hint: str | None = None
    route_tags: list[str] = Field(default_factory=list)


def _write_env_value(env_file: Path, key: str, value: str) -> None:
    lines: list[str] = []
    env_file.parent.mkdir(parents=True, exist_ok=True)
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    rendered = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = rendered
            break
    else:
        lines.append(rendered)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _routing_settings_payload(settings: Settings) -> dict[str, Any]:
    return {
        "llmproxy_routing_strategy": settings.llmproxy_routing_strategy,
        "llmproxy_frontier_default_entries": settings.llmproxy_frontier_default_entries,
    }


def _monitor_id_from_fields(provider_key: str, model_id: str, index: int) -> str:
    provider = "".join(ch if ch.isalnum() else "-" for ch in provider_key.lower()).strip("-") or "provider"
    model = "".join(ch if ch.isalnum() else "-" for ch in model_id.lower()).strip("-") or f"model-{index + 1}"
    return f"monitor-{provider}-{model}"


def _observability_payload(settings: Settings) -> dict[str, Any]:
    prometheus_path = "/metrics/prometheus"
    listeners = settings.admin_inbound_listeners()
    return {
        "prometheus": {
            "enabled": settings.llmproxy_prometheus_metrics_enabled,
            "path": prometheus_path,
            "scrape_config": {
                "job_name": "llmproxy",
                "metrics_path": prometheus_path,
                "static_configs": [{
                    "targets": [
                        f"{str(listener.get('published_host') or '127.0.0.1')}:{int(listener.get('published_port') or listener.get('port') or settings.llmproxy_api_port)}"
                        for listener in listeners
                    ],
                }],
            },
        },
        "logs_export": {
            "formats": ["ndjson"],
            "endpoint": "/admin/api/ops/logs/export",
        },
        "otel": {
            "enabled": settings.llmproxy_otel_enabled,
            "service_name": settings.llmproxy_otel_service_name,
            "exporter_otlp_endpoint": settings.llmproxy_otel_exporter_otlp_endpoint,
            "jaeger_ui_url": settings.llmproxy_jaeger_ui_url,
        },
    }


def _paged_payload(items: list[Any], *, total: int, limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _slice_items(items: list[Any], *, limit: int, offset: int) -> tuple[list[Any], int]:
    total = len(items)
    return items[offset:offset + limit], total


def _json_safe(value: Any) -> Any:
    return jsonable_encoder(value)


def _frontdoor_stream_listener(settings: Settings, listener_id: str | None) -> dict[str, Any]:
    listener = settings.resolve_inbound_listener(listener_id=listener_id)
    if not bool(listener.get("exposes_proxy")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selected listener does not expose the proxy front door.",
        )
    return listener


def _frontdoor_stream_base_url(listener: dict[str, Any]) -> str:
    protocol = str(listener.get("protocol") or "http").strip().lower() or "http"
    host = str(listener.get("published_host") or "127.0.0.1").strip() or "127.0.0.1"
    port = int(listener.get("published_port") or listener.get("port") or 80)
    return f"{protocol}://{host}:{port}"


def _frontdoor_stream_owner_id(execution_mode: str, owner_id: str | None) -> str | None:
    normalized = str(owner_id or "").strip()
    if normalized:
        return normalized
    if execution_mode == "training":
        return f"train_stream_probe_{uuid4().hex[:12]}"
    if execution_mode == "evaluation":
        return f"eval_stream_probe_{uuid4().hex[:12]}"
    return None


async def _collect_frontdoor_stream_result(
    *,
    base_url: str,
    token: str,
    payload: dict[str, Any],
    max_chunks: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    preview_chunks: list[str] = []
    chunk_count = 0
    finish_reason = None
    response_id = None
    stream_error = None
    buffer = ""
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        async with client.stream(
            "POST",
            f"{base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        ) as response:
            response.raise_for_status()
            async for text in response.aiter_text():
                buffer += text
                segments = buffer.split("\n\n")
                buffer = segments.pop() or ""
                for segment in segments:
                    data_line = next((line for line in segment.splitlines() if line.startswith("data: ")), None)
                    if data_line is None:
                        continue
                    raw = data_line[6:].strip()
                    if raw == "[DONE]":
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(event, dict) and isinstance(event.get("error"), dict):
                        stream_error = event["error"]
                        continue
                    if not isinstance(event, dict):
                        continue
                    if response_id is None and event.get("id"):
                        response_id = str(event["id"])
                    choices = event.get("choices")
                    if not isinstance(choices, list):
                        continue
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue
                        delta = choice.get("delta")
                        if isinstance(delta, dict):
                            content = str(delta.get("content") or "")
                            if content:
                                chunk_count += 1
                                if len(preview_chunks) < max_chunks:
                                    preview_chunks.append(content)
                        if choice.get("finish_reason"):
                            finish_reason = str(choice["finish_reason"])
    return {
        "response_id": response_id,
        "preview_text": "".join(preview_chunks),
        "chunk_preview": preview_chunks,
        "chunk_count": chunk_count,
        "finish_reason": finish_reason,
        "stream_error": stream_error,
    }


async def _run_frontdoor_stream_validation(
    *,
    request: StreamingValidationRequest,
    settings: Settings,
    session: Session,
    principal: AuthPrincipal,
) -> dict[str, Any]:
    listener = _frontdoor_stream_listener(settings, request.listener_id)
    base_url = _frontdoor_stream_base_url(listener)
    execution_mode = str(request.execution_mode or "interactive").strip().lower() or "interactive"
    owner_id = _frontdoor_stream_owner_id(execution_mode, request.owner_id)
    auth_token = principal.token
    ephemeral_key_id = None
    virtual_key_prefix = None
    if execution_mode in {"training", "evaluation"}:
        key_record, auth_token = create_virtual_key_record(
            session,
            VirtualKeyCreateRequest(
                display_name=f"{execution_mode.title()} streaming probe",
                owner_id=owner_id,
                role="api",
                models_allowed=[request.requested_model] if request.requested_model and request.requested_model != "proxy-auto" else [],
            ),
        )
        ephemeral_key_id = key_record.id
        virtual_key_prefix = key_record.key_prefix
    probe_session_id = f"admin_stream_probe_{uuid4().hex[:12]}"
    request_payload = {
        "model": request.requested_model,
        "stream": True,
        "messages": [{"role": "user", "content": request.prompt}],
        "metadata": {
            "session_id": probe_session_id,
            "domain_hint": request.domain_hint,
            "task_type_hint": request.task_type_hint,
        },
    }
    try:
        stream_result = await _collect_frontdoor_stream_result(
            base_url=base_url,
            token=auth_token,
            payload=request_payload,
            max_chunks=max(1, int(request.max_chunks or 12)),
            timeout_seconds=max(30.0, float(settings.llmproxy_provider_timeout_seconds) + 15.0),
        )
        stream_error = stream_result.get("stream_error")
        if isinstance(stream_error, dict):
            return _json_safe({
                "success": False,
                "listener_id": listener.get("listener_id"),
                "listener_url": base_url,
                "requested_model": request.requested_model,
                "execution_mode": execution_mode,
                "owner_id": owner_id,
                "response_id": stream_result.get("response_id"),
                "preview_text": stream_result.get("preview_text"),
                "chunk_preview": stream_result.get("chunk_preview"),
                "chunk_count": stream_result.get("chunk_count"),
                "finish_reason": stream_result.get("finish_reason"),
                "error": str(stream_error.get("message") or "Streaming request failed."),
                "error_type": stream_error.get("type"),
                "error_status_code": stream_error.get("status_code"),
                "validated_by": principal.role,
            })
        response_id = str(stream_result.get("response_id") or "")
        request_id = response_id.replace("chatcmpl_", "req_", 1) if response_id.startswith("chatcmpl_") else None
        request_row = session.get(RequestLog, request_id) if request_id else None
        if request_row is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="The streamed request completed, but the request record could not be verified.",
            )
        routing_decisions = list(
            session.execute(select(RoutingDecisionRecord).where(RoutingDecisionRecord.request_log_id == request_row.id)).scalars()
        )
        model_responses = list(
            session.execute(
                select(ModelResponse)
                .where(ModelResponse.request_log_id == request_row.id)
                .order_by(ModelResponse.created_at.asc())
            ).scalars()
        )
        candidates = list(
            session.execute(select(TrainingCandidate).where(TrainingCandidate.request_log_id == request_row.id)).scalars()
        )
        request_summary = request_summary_payload(request_row)
        latest_routing = routing_decision_payload(routing_decisions[-1]) if routing_decisions else {}
        selected_response = next((item for item in model_responses if item.response_role == "selected_response"), None)
        selected_response_payload = model_response_payload(selected_response) if selected_response is not None else {}
        candidate_payload = training_candidate_payload(candidates[-1]) if candidates else None
        traffic_origin = str(request_summary.get("traffic_origin") or "interactive")
        learning_pipeline_verified = (
            execution_mode in {"training", "evaluation"}
            and traffic_origin == "learning_pipeline"
            and str(request_summary.get("automation_owner_id") or "") == str(owner_id or "")
            and bool(candidates)
        )
        return _json_safe({
            "success": True,
            "listener_id": listener.get("listener_id"),
            "listener_url": base_url,
            "requested_model": request.requested_model,
            "execution_mode": execution_mode,
            "owner_id": owner_id,
            "virtual_key_prefix": virtual_key_prefix,
            "response_id": response_id,
            "request_id": request_row.id,
            "session_id": request_row.session_id,
            "provider_key": latest_routing.get("selected_provider"),
            "provider_family": latest_routing.get("selected_provider_family"),
            "model": latest_routing.get("selected_model") or selected_response_payload.get("model"),
            "selected_mode": latest_routing.get("selected_mode"),
            "preview_text": stream_result.get("preview_text"),
            "chunk_preview": stream_result.get("chunk_preview"),
            "chunk_count": stream_result.get("chunk_count"),
            "finish_reason": stream_result.get("finish_reason") or selected_response_payload.get("finish_reason"),
            "input_tokens": selected_response_payload.get("input_tokens"),
            "output_tokens": selected_response_payload.get("output_tokens"),
            "traffic_origin": traffic_origin,
            "automation_owner_id": request_summary.get("automation_owner_id"),
            "candidate_count": len(candidates),
            "candidate_id": candidate_payload.get("id") if candidate_payload else None,
            "candidate_captured": bool(candidates),
            "learning_pipeline_verified": learning_pipeline_verified,
            "verified_request": request_summary,
            "verified_routing": latest_routing,
            "verified_response": selected_response_payload,
            "verified_candidate": candidate_payload,
            "validated_by": principal.role,
        })
    finally:
        if ephemeral_key_id:
            disable_virtual_key_record(session, ephemeral_key_id)


def _stream_validation_requested_model(
    request: StreamingValidationRequest,
    *,
    provider_registry: dict[str, object],
) -> str:
    requested_model = str(request.requested_model or "").strip()
    if requested_model and requested_model != "proxy-auto":
        return requested_model
    provider_key = str(request.provider_key or "").strip()
    if provider_key:
        provider = provider_registry.get(provider_key)
        if provider is not None and getattr(provider, "model_id", None):
            return str(getattr(provider, "model_id"))
    return requested_model or "proxy-auto"


def _is_chat_capable_discovered_model(provider_key: str, model_id: str) -> bool:
    normalized_provider = str(provider_key or "").strip().lower()
    lower_model_id = str(model_id or "").strip().lower()
    if not lower_model_id:
        return False
    if normalized_provider in {"anthropic", "bedrock"}:
        return lower_model_id.startswith("claude")
    if normalized_provider in {"openai", "azure_openai"}:
        return lower_model_id.startswith(("gpt-", "chatgpt-", "o1", "o3", "o4", "codex-"))
    if normalized_provider == "google":
        return "gemini" in lower_model_id
    if normalized_provider == "xai":
        return lower_model_id.startswith("grok")
    if normalized_provider == "cohere":
        return lower_model_id.startswith("command")
    if normalized_provider == "perplexity":
        return "sonar" in lower_model_id
    if normalized_provider == "groq":
        return "llama" in lower_model_id or "qwen" in lower_model_id or "mixtral" in lower_model_id
    if normalized_provider == "mistral":
        return "mistral" in lower_model_id or "ministral" in lower_model_id
    if normalized_provider in {"deepseek", "together", "fireworks", "ollama", "vertex_ai", "huggingface_tgi"}:
        return True
    return True


def _streaming_validation_cache_key(request: StreamingValidationRequest) -> str:
    return "|".join(
        [
            str(request.provider_key or "").strip().lower(),
            str(request.listener_id or "").strip().lower(),
            str(request.execution_mode or "").strip().lower(),
            str(request.validation_scope or "").strip().lower(),
            str(request.target_filter or "").strip().lower(),
            str(request.prompt or "").strip(),
        ]
    )


async def _stream_validation_plan(
    *,
    request: StreamingValidationRequest,
    settings: Settings,
    session: Session,
) -> dict[str, Any]:
    provider_registry = get_provider_registry(settings, session=session)
    default_requested_model = _stream_validation_requested_model(request, provider_registry=provider_registry)
    provider_key = str(request.provider_key or "").strip()
    if request.validation_scope == "default_only":
        return {
            "provider_registry": provider_registry,
            "requested_model": default_requested_model,
            "targets": [default_requested_model],
            "discovered_model_count": 1 if default_requested_model else 0,
            "streamable_model_count": 1 if default_requested_model else 0,
            "skipped_models": [],
        }
    if not provider_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider key is required for all-discovered validation scope.",
        )
    capabilities = await list_provider_capabilities_async(settings, session=session)
    discovered_models: list[str] = []
    streamable_models: list[str] = []
    subset_models: list[str] = []
    skipped_models: list[str] = []
    for capability in capabilities:
        if str(getattr(capability, "provider_name", "") or "") != provider_key:
            continue
        model_id = str(getattr(capability, "model_id", "") or "").strip()
        if not model_id:
            continue
        discovered_models.append(model_id)
        if bool(getattr(capability, "supports_streaming", False)):
            streamable_models.append(model_id)
            if _is_chat_capable_discovered_model(provider_key, model_id):
                subset_models.append(model_id)
        else:
            skipped_models.append(model_id)
    candidate_models = subset_models if request.target_filter == "chat_capable_subset" else streamable_models
    targets: list[str] = []
    seen: set[str] = set()
    for model_id in [default_requested_model, *candidate_models]:
        normalized = str(model_id or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        targets.append(normalized)
    if not targets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No matching discovered models are available for provider '{provider_key}'.",
        )
    return {
        "provider_registry": provider_registry,
        "requested_model": default_requested_model,
        "targets": targets,
        "discovered_model_count": len(discovered_models),
        "streamable_model_count": len(streamable_models),
        "chat_capable_subset_count": len(subset_models),
        "skipped_models": skipped_models,
    }


def _stream_validation_failure_result(
    *,
    request: StreamingValidationRequest,
    requested_model: str,
    principal: AuthPrincipal,
    error: Exception | str,
) -> dict[str, Any]:
    return {
        "success": False,
        "requested_model": requested_model,
        "provider_key": request.provider_key,
        "execution_mode": request.execution_mode,
        "owner_id": request.owner_id,
        "error": str(error),
        "validated_by": principal.role,
    }


async def _run_frontdoor_stream_validation_suite(
    *,
    request: StreamingValidationRequest,
    settings: Settings,
    session: Session,
    principal: AuthPrincipal,
) -> dict[str, Any]:
    cache_key = _streaming_validation_cache_key(request)
    if request.validation_scope != "default_only" and request.use_cached_results:
        cached = STREAMING_VALIDATION_SUITE_CACHE.get(cache_key)
        if cached:
            age_seconds = max(
                0,
                int(
                    (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(cached["cached_at"]))
                    ).total_seconds()
                ),
            )
            if age_seconds <= int(request.cache_ttl_seconds):
                payload = dict(cached["result"])
                payload["cache_hit"] = True
                payload["cached_at"] = cached["cached_at"]
                payload["cache_age_seconds"] = age_seconds
                return _json_safe(payload)
    plan = await _stream_validation_plan(request=request, settings=settings, session=session)
    requested_model = str(plan.get("requested_model") or request.requested_model or "proxy-auto")
    if request.validation_scope == "default_only":
        result = await _run_frontdoor_stream_validation(
            request=request.model_copy(update={"requested_model": requested_model}),
            settings=settings,
            session=session,
            principal=principal,
        )
        result["validation_scope"] = request.validation_scope
        result["target_count"] = 1
        result["validated_count"] = 1 if result.get("success") else 0
        result["failed_count"] = 0 if result.get("success") else 1
        result["discovered_model_count"] = int(plan.get("discovered_model_count") or 1)
        result["streamable_model_count"] = int(plan.get("streamable_model_count") or 1)
        result["chat_capable_subset_count"] = int(plan.get("chat_capable_subset_count") or result["streamable_model_count"])
        result["skipped_model_count"] = len(plan.get("skipped_models") or [])
        return result

    session_factory = get_session_factory()
    semaphore = asyncio.Semaphore(max(1, int(request.max_concurrency or 6)))

    async def _probe_model(model_id: str) -> dict[str, Any]:
        async with semaphore:
            probe_session = session_factory()
            try:
                return await _run_frontdoor_stream_validation(
                    request=request.model_copy(update={"requested_model": model_id}),
                    settings=settings,
                    session=probe_session,
                    principal=principal,
                )
            except Exception as exc:
                return _stream_validation_failure_result(
                    request=request,
                    requested_model=model_id,
                    principal=principal,
                    error=exc,
                )
            finally:
                probe_session.close()

    started_at = perf_counter()
    results = list(await asyncio.gather(*(_probe_model(model_id) for model_id in plan["targets"])))
    successful_results = [item for item in results if item.get("success")]
    failed_results = [item for item in results if not item.get("success")]
    provider_registry = plan["provider_registry"]
    provider = provider_registry.get(str(request.provider_key or "").strip()) if str(request.provider_key or "").strip() else None
    payload = {
        "success": not failed_results,
        "suite": True,
        "validation_scope": request.validation_scope,
        "target_filter": request.target_filter,
        "provider_key": request.provider_key,
        "provider_family": getattr(provider, "provider_family", request.provider_key),
        "listener_id": request.listener_id,
        "requested_model": requested_model,
        "execution_mode": request.execution_mode,
        "owner_id": request.owner_id,
        "max_concurrency": int(request.max_concurrency or 6),
        "target_count": len(results),
        "validated_count": len(successful_results),
        "failed_count": len(failed_results),
        "discovered_model_count": int(plan.get("discovered_model_count") or 0),
        "streamable_model_count": int(plan.get("streamable_model_count") or 0),
        "chat_capable_subset_count": int(plan.get("chat_capable_subset_count") or 0),
        "skipped_model_count": len(plan.get("skipped_models") or []),
        "skipped_models": plan.get("skipped_models") or [],
        "elapsed_ms": int((perf_counter() - started_at) * 1000),
        "results": results,
        "validated_by": principal.role,
        "cache_hit": False,
    }
    cached_at = datetime.now(timezone.utc).isoformat()
    STREAMING_VALIDATION_SUITE_CACHE[cache_key] = {"cached_at": cached_at, "result": payload}
    payload["cached_at"] = cached_at
    payload["cache_age_seconds"] = 0
    return _json_safe(payload)


def _guardrails_payload(settings: Settings) -> dict[str, Any]:
    return {
        "prompt_injection_blocking_enabled": settings.llmproxy_guardrail_block_prompt_injection,
        "pii_output_masking_enabled": settings.llmproxy_guardrail_mask_pii_output,
        "pre_hooks": list(settings.llmproxy_guardrail_pre_hooks or []),
        "post_hooks": list(settings.llmproxy_guardrail_post_hooks or []),
        "blocked_output_patterns": list(settings.llmproxy_guardrail_blocked_output_patterns or []),
    }


def _streaming_route_examples(session: Session, settings: Settings) -> list[dict[str, Any]]:
    scenarios = [
        {"requested_model": "proxy-local", "domain_hint": "coding", "task_type_hint": "analysis"},
        {"requested_model": "proxy-auto", "domain_hint": "coding", "task_type_hint": "code_review"},
        {"requested_model": "proxy-auto", "domain_hint": "software_architecture", "task_type_hint": "design_review"},
        {"requested_model": "proxy-auto", "domain_hint": "research", "task_type_hint": "analysis"},
        {"requested_model": "proxy-auto", "domain_hint": "general", "task_type_hint": "analysis"},
    ]
    provider_registry = get_provider_registry(settings, session=session)
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        request = ChatCompletionRequest.model_validate(
            {
                "model": scenario["requested_model"],
                "messages": [{"role": "user", "content": "streaming validation example"}],
                "metadata": {
                    "session_id": "admin_streaming_support",
                    "domain_hint": scenario["domain_hint"],
                    "task_type_hint": scenario["task_type_hint"],
                },
            }
        )
        classification = classify_request(request)
        route = select_route("req_admin_streaming_support", request, classification, settings, session=session)
        provider = resolve_provider(
            settings,
            provider_registry,
            provider_key=route.provider_key,
            entry=route.entry_index.get(route.provider_key),
        )
        rows.append(
            {
                **scenario,
                "selected_provider": route.provider_key,
                "selected_model": route.decision.selected_model,
                "selected_mode": route.decision.selected_mode,
                "supports_streaming": bool(getattr(provider, "supports_streaming", False)),
            }
        )
    return rows


async def _mcp_server_payloads(settings: Settings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for server_name, raw in settings.llmproxy_mcp_servers.items():
        config = raw if isinstance(raw, dict) else {}
        tools: list[dict[str, object]] = []
        error: str | None = None
        try:
            tools = await _list_mcp_tools(settings, server_name)
        except Exception as exc:
            error = str(exc)
        rows.append(
            {
                "server": server_name,
                "transport": str(config.get("transport", "stdio")),
                "command": str(config.get("command", "")),
                "cwd": config.get("cwd"),
                "timeout_seconds": float(config.get("timeout_seconds", 30.0)),
                "configured": bool(config.get("command")),
                "tool_count": len(tools),
                "tools": [
                    {
                        "name": str(item.get("name", "")),
                        "description": item.get("description"),
                        "input_schema": item.get("inputSchema"),
                    }
                    for item in tools
                ],
                "error": error,
            }
        )
    return rows


def _provider_guides(settings: Settings) -> list[dict[str, Any]]:
    return [
        {
            "provider_key": "cloudflare_workers_ai",
            "label": "Cloudflare Workers AI",
            "provider_family": "Cloudflare Workers AI",
            "configured": settings.provider_configuration.get("cloudflare_workers_ai", False),
            "config_keys": [
                "LLMPROXY_CLOUDFLARE_API_TOKEN",
                "LLMPROXY_CLOUDFLARE_ACCOUNT_ID",
                "LLMPROXY_CLOUDFLARE_WORKERS_AI_MODEL",
                "LLMPROXY_CLOUDFLARE_GATEWAY_ID",
            ],
            "recommended_base_url": settings.llmproxy_cloudflare_base_url,
            "validation_mode": "native_chat",
            "notes": [
                "Uses Cloudflare's native /accounts/{account_id}/ai/run/{model} API.",
                "Requires Cloudflare account-scoped auth rather than OpenAI API keys.",
                "Gateway ID is optional but recommended when routing through AI Gateway.",
            ],
        },
        {
            "provider_key": "huggingface_tgi",
            "label": "HuggingFace TGI",
            "provider_family": "HuggingFace TGI",
            "configured": settings.provider_configuration.get("huggingface_tgi", False),
            "config_keys": [
                "LLMPROXY_HUGGINGFACE_TGI_BASE_URL",
                "LLMPROXY_HUGGINGFACE_TGI_MODEL",
                "LLMPROXY_HUGGINGFACE_TGI_API_KEY",
            ],
            "recommended_base_url": settings.llmproxy_huggingface_tgi_base_url,
            "validation_mode": "openai_compatible",
            "notes": [
                "Targets TGI Messages API /v1/chat/completions.",
                "Works as a named provider and as local runtime='tgi'.",
                "API key is optional for self-hosted endpoints.",
            ],
        },
        {
            "provider_key": "replicate",
            "label": "Replicate",
            "provider_family": "Replicate Predictions",
            "configured": settings.provider_configuration.get("replicate", False),
            "config_keys": [
                "LLMPROXY_REPLICATE_API_TOKEN",
                "LLMPROXY_REPLICATE_BASE_URL",
            ],
            "recommended_base_url": settings.llmproxy_replicate_base_url,
            "validation_mode": "prediction_job",
            "notes": [
                "Replicate is exposed as a prediction/job backend, not a chat-completions provider.",
                "Use model IDs accepted by POST /v1/predictions, such as owner/name or owner/name:version.",
                "Prediction results are persisted on the queued job payload for operator inspection.",
            ],
        },
    ]


def _record_integration_activity(
    session: Session | None,
    *,
    settings: Settings,
    event_type: str,
    source: str,
    component: str,
    message: str,
    payload: dict[str, Any],
    success: bool,
) -> None:
    emit_event(
        session,
        event_type=event_type,
        source=source,
        payload=payload,
    )
    if session is not None and hasattr(session, "commit"):
        try:
            session.commit()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
    log_record(
        settings,
        level="INFO" if success else "ERROR",
        component=component,
        category="integration",
        message=message,
        data=payload,
        audit=True,
    )

@router.get("")
def admin_console() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@router.get("/static/{asset_path:path}")
def admin_static(asset_path: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / asset_path)


@router.get("/api/config", dependencies=[Depends(require_api_token)])
def get_config(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return settings_payload(settings)


@router.get("/api/routing/settings", dependencies=[Depends(require_api_token)])
def get_routing_settings(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return _routing_settings_payload(settings)


@router.post("/api/routing/settings", dependencies=[Depends(require_operator_token)])
def set_routing_settings(
    request: RoutingSettingsUpdateRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    env_file = Path(request.env_file)
    _write_env_value(env_file, "LLMPROXY_ROUTING_STRATEGY", request.routing_strategy)
    _write_env_value(env_file, "LLMPROXY_FRONTIER_DEFAULT_ENTRIES", json.dumps(request.frontier_default_entries))
    log_record(
        settings,
        level="INFO",
        component="admin.routing",
        category="audit",
        message="Routing settings updated",
        data={
            "routing_strategy": request.routing_strategy,
            "frontier_default_entry_count": len(request.frontier_default_entries),
            "env_file": str(env_file),
        },
        audit=True,
    )
    return {
        "saved": True,
        "env_file": str(env_file),
        "routing_strategy": request.routing_strategy,
        "frontier_default_entry_count": len(request.frontier_default_entries),
    }


@router.post("/api/config/inbound-listeners", dependencies=[Depends(require_operator_token)])
def set_inbound_listeners(
    request: InboundListenerConfigUpdateRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    env_file = Path(request.env_file)
    rendered = [listener.model_dump(mode="json") for listener in request.listeners]
    _write_env_value(env_file, "LLMPROXY_INBOUND_LISTENERS", json.dumps(rendered))
    preview_settings = Settings(llmproxy_inbound_listeners=rendered)
    log_record(
        settings,
        level="INFO",
        component="admin.config",
        category="audit",
        message="Inbound listener topology updated",
        data={"env_file": str(env_file), "listener_count": len(rendered)},
        audit=True,
    )
    return {
        "updated": True,
        "env_file": str(env_file),
        "restart_required": True,
        "listeners": preview_settings.configured_inbound_listeners(),
    }


@router.get("/api/ops/model-monitors", dependencies=[Depends(require_api_token)])
def get_model_monitors(
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = list_model_monitors(session, settings)
    return {
        "monitor_count": len(rows),
        "enabled_count": sum(1 for row in rows if row.get("enabled")),
        "due_count": sum(1 for row in rows if row.get("due_now")),
        "monitors": rows,
    }


@router.post("/api/config/model-monitors", dependencies=[Depends(require_operator_token)])
def set_model_monitors(
    request: ModelMonitorConfigUpdateRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    env_file = Path(request.env_file)
    rendered: list[dict[str, Any]] = []
    for index, monitor in enumerate(request.monitors):
        payload = monitor.model_dump(mode="json")
        payload["monitor_id"] = payload.get("monitor_id") or _monitor_id_from_fields(
            str(payload.get("provider_key") or ""),
            str(payload.get("model_id") or ""),
            index,
        )
        rendered.append(payload)
    _write_env_value(env_file, "LLMPROXY_MODEL_MONITORS", json.dumps(rendered))
    get_settings.cache_clear()
    preview_settings = Settings(llmproxy_model_monitors=rendered)
    log_record(
        settings,
        level="INFO",
        component="admin.config",
        category="audit",
        message="Model monitor configuration updated",
        data={"env_file": str(env_file), "monitor_count": len(rendered)},
        audit=True,
    )
    return {
        "updated": True,
        "env_file": str(env_file),
        "restart_required": True,
        "monitors": preview_settings.configured_model_monitors(),
    }


@router.post("/api/ops/model-monitors/{monitor_id}/run", dependencies=[Depends(require_operator_token)])
async def run_model_monitor_now(
    monitor_id: str,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
    principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    monitor = next(
        (item for item in settings.configured_model_monitors() if str(item.get("monitor_id")) == monitor_id),
        None,
    )
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model monitor not found.")
    return await run_model_monitor(
        session,
        settings=settings,
        monitor=monitor,
        operator_token=principal.token,
    )


@router.get("/api/mcp/servers", dependencies=[Depends(require_api_token)])
async def get_mcp_servers(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    rows = await _mcp_server_payloads(settings)
    if paginated:
        items, total = _slice_items(rows, limit=limit, offset=offset)
        return _paged_payload(items, total=total, limit=limit, offset=offset)
    return {
        "server_count": len(rows),
        "tool_count": sum(int(item.get("tool_count", 0)) for item in rows),
        "servers": rows,
    }


@router.get("/api/a2a/peers", dependencies=[Depends(require_api_token)])
async def get_a2a_peers(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    rows = await list_a2a_peers(settings)
    if paginated:
        items, total = _slice_items(rows, limit=limit, offset=offset)
        return _paged_payload(items, total=total, limit=limit, offset=offset)
    return {
        "peer_count": len(rows),
        "capability_count": sum(int(item.get("capability_count", 0)) for item in rows),
        "peers": rows,
    }


@router.get("/api/rest/endpoints", dependencies=[Depends(require_api_token)])
async def get_rest_endpoints(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    rows = await list_rest_endpoints(settings)
    if paginated:
        items, total = _slice_items(rows, limit=limit, offset=offset)
        return _paged_payload(items, total=total, limit=limit, offset=offset)
    return {
        "endpoint_count": len(rows),
        "configured_count": sum(int(bool(item.get("configured"))) for item in rows),
        "endpoints": rows,
    }


@router.get("/api/providers/guides", dependencies=[Depends(require_api_token)])
def get_provider_guides(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    guides = _provider_guides(settings)
    if paginated:
        items, total = _slice_items(guides, limit=limit, offset=offset)
        return _paged_payload(items, total=total, limit=limit, offset=offset)
    return {
        "provider_count": len(guides),
        "providers": guides,
    }


@router.get("/api/pricing/catalog", dependencies=[Depends(require_api_token)])
def get_pricing_catalog() -> dict[str, Any]:
    rows = pricing_catalog()
    return {"count": len(rows), "items": rows}


@router.get("/api/observability", dependencies=[Depends(require_api_token)])
def get_observability_settings(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return _observability_payload(settings)


@router.get("/api/topology/routing-inventory", dependencies=[Depends(require_api_token)])
def get_routing_topology_inventory(
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return build_routing_topology_inventory(session)


@router.get("/api/guardrails/settings", dependencies=[Depends(require_operator_token)])
def get_guardrails_settings(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return _guardrails_payload(settings)


@router.get("/api/prompts", dependencies=[Depends(require_api_token)])
def get_prompt_templates(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    metrics_by_key = build_prompt_template_metrics(session)
    family_rollouts: dict[str, dict[str, Any]] = {}
    rows = []
    for item in list_prompt_templates(session):
        family_rollouts.setdefault(item.name, prompt_family_rollout_payload(session, name=item.name))
        payload = prompt_template_payload(item)
        payload["metrics"] = metrics_by_key.get((item.name, int(item.version)), {})
        payload["family_rollout"] = family_rollouts[item.name]
        rows.append(payload)
    if not paginated:
        return rows
    items, total = _slice_items(rows, limit=limit, offset=offset)
    return _paged_payload(items, total=total, limit=limit, offset=offset)


@router.post("/api/prompts", dependencies=[Depends(require_operator_token)], status_code=status.HTTP_201_CREATED)
def create_prompt_template_api(
    request: PromptTemplateAdminCreateRequest,
    session: Session = Depends(get_session),
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
    payload["metrics"] = build_prompt_template_metrics(session).get((record.name, int(record.version)), {})
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    return payload


@router.get("/api/prompts/{name}", dependencies=[Depends(require_api_token)])
def get_prompt_template_api(
    name: str,
    version: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = get_prompt_template(session, name=name, version=version)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found.")
    payload = prompt_template_payload(record)
    payload["metrics"] = build_prompt_template_metrics(session).get((record.name, int(record.version)), {})
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    return payload


@router.post("/api/prompts/{name}/render", dependencies=[Depends(require_api_token)])
def render_prompt_template_api(
    name: str,
    request: PromptTemplateAdminRenderRequest,
    session: Session = Depends(get_session),
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
    payload["metrics"] = build_prompt_template_metrics(session).get((record.name, int(record.version)), {})
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    payload["rendered_text"] = rendered
    payload["render_variables"] = request.variables
    return payload


@router.post("/api/prompts/{name}/{version}/status", dependencies=[Depends(require_operator_token)])
def update_prompt_template_status_api(
    name: str,
    version: int,
    request: PromptTemplateAdminStatusUpdateRequest,
    session: Session = Depends(get_session),
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
    payload["metrics"] = build_prompt_template_metrics(session).get((record.name, int(record.version)), {})
    payload["family_rollout"] = prompt_family_rollout_payload(session, name=record.name)
    return payload


@router.get("/api/prompts/{name}/comparison", dependencies=[Depends(require_api_token)])
def compare_prompt_template_api(
    name: str,
    baseline_version: int | None = Query(default=None),
    compare_version: int | None = Query(default=None),
    session: Session = Depends(get_session),
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


@router.post("/api/prompts/{name}/rollout", dependencies=[Depends(require_operator_token)])
def update_prompt_template_rollout_api(
    name: str,
    request: PromptTemplateAdminRolloutRequest,
    session: Session = Depends(get_session),
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


@router.post("/api/prompts/{name}/promote-challenger", dependencies=[Depends(require_operator_token)])
def promote_prompt_template_challenger_api(
    name: str,
    challenger_version: int | None = Query(default=None),
    session: Session = Depends(get_session),
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


@router.post("/api/prompts/{name}/auto-promotion-policy", dependencies=[Depends(require_operator_token)])
def update_prompt_template_auto_promotion_policy_api(
    name: str,
    request: PromptTemplateAdminAutoPromotionPolicyRequest,
    session: Session = Depends(get_session),
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


@router.post("/api/prompts/{name}/auto-promotion/evaluate", dependencies=[Depends(require_operator_token)])
def evaluate_prompt_template_auto_promotion_api(
    name: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        return evaluate_prompt_auto_promotion(session, name=name)
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.get("/api/prompts/{name}/diff", dependencies=[Depends(require_api_token)])
def diff_prompt_template_api(
    name: str,
    from_version: int,
    to_version: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        return diff_prompt_templates(session, name=name, from_version=from_version, to_version=to_version)
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/api/proxy/route-preview", dependencies=[Depends(require_api_token)])
def preview_proxy_route(
    request: RoutePreviewRequest,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    chat_request = ChatCompletionRequest.model_validate(
        {
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "messages": request.messages,
            "metadata": {
                "session_id": request.session_id,
                "listener_id": request.listener_id,
                "domain_hint": request.domain_hint,
                "task_type_hint": request.task_type_hint,
                "region_hint": request.region_hint,
                "route_tags": request.route_tags,
            },
        }
    )
    classification = classify_request(chat_request)
    route = select_route("req_admin_route_preview", chat_request, classification, settings, session=session)
    return {
        "classification": classification,
        "selected_provider": route.provider_key,
        "shadow_provider_keys": list(route.shadow_provider_keys),
        "selected_entry": route.selected_entry,
        "decision": route.decision.model_dump(),
    }


@router.post("/api/mcp/servers/{server_name}/validate", dependencies=[Depends(require_operator_token)])
async def validate_mcp_server(
    server_name: str,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    try:
        return await inspect_mcp_server(settings, server_name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MCP server validation failed: {exc}",
        ) from exc


@router.post("/api/a2a/peers/{peer_name}/validate", dependencies=[Depends(require_operator_token)])
async def validate_a2a_peer(
    peer_name: str,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        payload = await inspect_a2a_peer(settings, peer_name)
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.a2a.validated",
            source=peer_name,
            component="admin.a2a",
            message="A2A peer validated",
            payload=payload,
            success=bool(payload.get("validated")),
        )
        return payload
    except HTTPException as exc:
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.a2a.validated",
            source=peer_name,
            component="admin.a2a",
            message="A2A peer validation failed",
            payload={"peer": peer_name, "success": False, "error": exc.detail},
            success=False,
        )
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"A2A peer validation failed: {exc}",
        ) from exc


@router.post("/api/a2a/peers/{peer_name}/invoke", dependencies=[Depends(require_operator_token)])
async def invoke_configured_a2a_peer(
    peer_name: str,
    request: A2APeerInvokeRequest,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        payload = await invoke_a2a_peer(
            settings,
            peer_name,
            capability=request.capability,
            input_payload=request.input,
        )
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.a2a.invoked",
            source=peer_name,
            component="admin.a2a",
            message="A2A peer invoked",
            payload=payload,
            success=bool(payload.get("invoked")),
        )
        return payload
    except HTTPException as exc:
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.a2a.invoked",
            source=peer_name,
            component="admin.a2a",
            message="A2A peer invocation failed",
            payload={
                "peer": peer_name,
                "capability": request.capability,
                "input": request.input,
                "success": False,
                "error": exc.detail,
            },
            success=False,
        )
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"A2A peer invocation failed: {exc}",
        ) from exc


@router.post("/api/rest/endpoints/{endpoint_name}/validate", dependencies=[Depends(require_operator_token)])
async def validate_rest_endpoint(
    endpoint_name: str,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        payload = await inspect_rest_endpoint(settings, endpoint_name)
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.rest.validated",
            source=endpoint_name,
            component="admin.rest",
            message="REST endpoint validated",
            payload=payload,
            success=bool(payload.get("validated")),
        )
        return payload
    except HTTPException as exc:
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.rest.validated",
            source=endpoint_name,
            component="admin.rest",
            message="REST endpoint validation failed",
            payload={"endpoint_name": endpoint_name, "success": False, "error": exc.detail},
            success=False,
        )
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"REST endpoint validation failed: {exc}",
        ) from exc


@router.post("/api/rest/endpoints/{endpoint_name}/invoke", dependencies=[Depends(require_operator_token)])
async def invoke_configured_rest_endpoint(
    endpoint_name: str,
    request: RestEndpointInvokeRequest,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        payload = await invoke_rest_endpoint(
            settings,
            endpoint_name,
            method=request.method,
            path=request.path,
            input_payload=request.input,
        )
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.rest.invoked",
            source=endpoint_name,
            component="admin.rest",
            message="REST endpoint invoked",
            payload=payload,
            success=bool(payload.get("invoked")),
        )
        return payload
    except HTTPException as exc:
        _record_integration_activity(
            session,
            settings=settings,
            event_type="integration.rest.invoked",
            source=endpoint_name,
            component="admin.rest",
            message="REST endpoint invocation failed",
            payload={
                "endpoint_name": endpoint_name,
                "method": request.method,
                "path": request.path,
                "input": request.input,
                "success": False,
                "error": exc.detail,
            },
            success=False,
        )
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"REST endpoint invocation failed: {exc}",
        ) from exc


@router.get("/api/auth/virtual-keys", dependencies=[Depends(require_operator_token)])
def list_virtual_keys(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    session: Session = Depends(get_session),
) -> list[VirtualKeyView] | dict[str, Any]:
    rows = list_virtual_key_records(session)
    payload = [VirtualKeyView.model_validate(virtual_key_payload(item)) for item in rows]
    if not paginated:
        return payload
    items, total = _slice_items(payload, limit=limit, offset=offset)
    return _paged_payload([item.model_dump(mode="json") for item in items], total=total, limit=limit, offset=offset)


@router.post("/api/auth/virtual-keys", response_model=VirtualKeyCreateResponse, dependencies=[Depends(require_operator_token)])
def create_virtual_key(
    request: VirtualKeyCreateRequest,
    session: Session = Depends(get_session),
) -> VirtualKeyCreateResponse:
    record, raw_token = create_virtual_key_record(session, request)
    payload = virtual_key_payload(record)
    payload["token"] = raw_token
    return VirtualKeyCreateResponse.model_validate(payload)


@router.post("/api/auth/virtual-keys/{key_id}/disable", response_model=VirtualKeyView, dependencies=[Depends(require_operator_token)])
def disable_virtual_key(
    key_id: str,
    session: Session = Depends(get_session),
) -> VirtualKeyView:
    record = disable_virtual_key_record(session, key_id)
    return VirtualKeyView.model_validate(virtual_key_payload(record))


@router.patch("/api/auth/virtual-keys/{key_id}", response_model=VirtualKeyView, dependencies=[Depends(require_operator_token)])
def update_virtual_key(
    key_id: str,
    request: VirtualKeyUpdateRequest,
    session: Session = Depends(get_session),
) -> VirtualKeyView:
    record = update_virtual_key_record(session, key_id, request)
    return VirtualKeyView.model_validate(virtual_key_payload(record))


@router.post("/api/auth/virtual-keys/{key_id}/rotate", response_model=VirtualKeyRotateResponse, dependencies=[Depends(require_operator_token)])
def rotate_virtual_key(
    key_id: str,
    session: Session = Depends(get_session),
) -> VirtualKeyRotateResponse:
    record, raw_token, previous_key_prefix = rotate_virtual_key_record(session, key_id)
    payload = virtual_key_payload(record)
    payload["token"] = raw_token
    payload["previous_key_prefix"] = previous_key_prefix
    return VirtualKeyRotateResponse.model_validate(payload)


@router.get("/api/proxy/streaming-support", dependencies=[Depends(require_api_token)])
def get_streaming_support(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    capabilities = [item.model_dump(mode="json") for item in list_provider_capabilities(settings, session=session)]
    provider_configuration = settings_payload(settings)["provider_configuration"]
    for item in capabilities:
        item["configured"] = bool(provider_configuration.get(item["provider_name"], False))
    return {
        "providers": capabilities,
        "route_examples": _streaming_route_examples(session, settings),
    }


@router.get("/api/config/validate", dependencies=[Depends(require_api_token)])
def validate_config(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    from app.db.session import get_engine

    with get_engine().connect() as connection:
        connection.execute(text("select 1"))
    return {
        "database_connection": "ok",
        "reports_path_exists": Path(settings.llmproxy_reports_path).exists(),
        "models_path_exists": Path(settings.llmproxy_models_path).exists(),
        "logs_path_exists": Path(settings.llmproxy_logs_path).exists(),
        "provider_configuration": settings_payload(settings)["provider_configuration"],
        "provider_guides": _provider_guides(settings),
    }


@router.get("/api/models/local-runtimes", dependencies=[Depends(require_api_token)])
def get_local_runtime_status(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]]:
    return build_local_runtime_status(session, settings)


@router.post("/api/config/set", dependencies=[Depends(require_operator_token)])
def set_config_value(request: ConfigSetRequest) -> dict[str, Any]:
    env_file = Path(request.env_file)
    _write_env_value(env_file, request.key, request.value)
    log_record(
        get_runtime_settings(),
        level="INFO",
        component="admin.config",
        category="audit",
        message="Configuration value updated",
        data={"env_file": str(env_file), "key": request.key},
        audit=True,
    )
    return {"updated": True, "env_file": str(env_file), "key": request.key, "value": request.value}


@router.get("/api/ops/summary", dependencies=[Depends(require_api_token)])
def get_operations_summary(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return build_operations_summary(session, settings=settings)


@router.get("/api/ops/llm-timeseries", dependencies=[Depends(require_api_token)])
def get_llm_timeseries(
    provider_key: str,
    model_id: str | None = None,
    window_hours: int = Query(default=168, ge=1, le=24 * 90),
    bucket_minutes: int = Query(default=60, ge=1, le=24 * 60),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    normalized_provider_key = str(provider_key or "").strip()
    if not normalized_provider_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="provider_key is required.")
    return build_llm_timeseries(
        session,
        settings=settings,
        provider_key=normalized_provider_key,
        model_id=str(model_id or "").strip() or None,
        window_hours=window_hours,
        bucket_minutes=bucket_minutes,
    )


@router.get("/api/ops/logs", dependencies=[Depends(require_api_token)])
def get_operations_logs(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    listener_id: str | None = None,
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]] | dict[str, Any]:
    rows = tail_log_records(
        settings,
        limit=limit,
        offset=offset,
        level=level,
        component=component,
        category=category,
        listener_id=listener_id,
    )
    if not paginated:
        return rows
    total = len(
        tail_log_records(
            settings,
            limit=100_000_000,
            offset=0,
            level=level,
            component=component,
            category=category,
            listener_id=listener_id,
        )
    )
    return _paged_payload(rows, total=total, limit=limit, offset=offset)


@router.get("/api/ops/events", dependencies=[Depends(require_api_token)])
def get_operational_events(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    history_scope: str = Query(default="active", pattern="^(active|all|historical)$"),
    event_class: str | None = Query(default=None, pattern="^(log|error|audit|job|runtime_event|request)$"),
    event_source: str | None = Query(default=None, pattern="^(ops_log|job|runtime_event|request)$"),
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    listener_id: str | None = None,
    selected_provider: str | None = None,
    selected_model: str | None = None,
    selected_pool_id: str | None = None,
    selected_node_id: str | None = None,
    prompt_template_name: str | None = None,
    prompt_template_version: int | None = None,
    prompt_template_selection_mode: str | None = Query(default=None, pattern="^(active|challenger_canary|explicit)$"),
    traffic_origin: str | None = None,
    automation_scope: str | None = None,
    domain: str | None = None,
    task_type: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    promotable_only: bool = False,
    sort_by: str = Query(default="timestamp", pattern="^(timestamp|event_class|event_source|level|component|category|listener_id|message|requested_model|selected_provider|selected_model|latency_ms|first_response_latency_ms|cost_estimate|input_tokens|output_tokens|total_tokens|traffic_origin|domain|task_type)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    if not isinstance(prompt_template_selection_mode, str):
        prompt_template_selection_mode = None
    created_after_dt: datetime | None = None
    created_before_dt: datetime | None = None
    historical_cutoff = datetime.now(timezone.utc) - timedelta(hours=OPS_EVENTS_ACTIVE_WINDOW_HOURS)
    if created_after:
        try:
            created_after_dt = datetime.fromisoformat(str(created_after).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="created_after must be an ISO timestamp.") from exc
    if created_before:
        try:
            created_before_dt = datetime.fromisoformat(str(created_before).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="created_before must be an ISO timestamp.") from exc

    page_window = max(limit + offset, limit)
    log_scan_limit = min(
        max(page_window * OPS_EVENTS_SCAN_MULTIPLIER, OPS_EVENTS_MIN_SCAN_LIMIT),
        OPS_EVENTS_MAX_SCAN_LIMIT,
    )
    secondary_scan_limit = min(
        max(page_window * 4, OPS_EVENTS_SECONDARY_MIN_SCAN_LIMIT),
        OPS_EVENTS_SECONDARY_MAX_SCAN_LIMIT,
    )
    if history_scope in {"all", "historical"}:
        log_scan_limit = min(
            max(log_scan_limit * OPS_EVENTS_HISTORY_SCAN_MULTIPLIER, OPS_EVENTS_MIN_SCAN_LIMIT),
            OPS_EVENTS_HISTORY_MAX_SCAN_LIMIT,
        )
        secondary_scan_limit = min(
            max(secondary_scan_limit * OPS_EVENTS_HISTORY_SCAN_MULTIPLIER, OPS_EVENTS_SECONDARY_MIN_SCAN_LIMIT),
            OPS_EVENTS_SECONDARY_HISTORY_MAX_SCAN_LIMIT,
        )

    include_logs = event_source in {None, "ops_log"} and event_class not in {"job", "runtime_event"}
    include_jobs = event_source in {None, "job"} and event_class in {None, "job"}
    include_runtime_events = event_source in {None, "runtime_event"} and event_class in {None, "runtime_event"}
    include_requests = event_source in {None, "request"} and event_class in {None, "request"}

    normalized: list[dict[str, Any]] = []
    if include_logs:
        log_rows = tail_log_records(
            settings,
            limit=log_scan_limit,
            offset=0,
            level=level,
            component=component,
            category=category,
            listener_id=listener_id,
            audit_only=event_class == "audit",
            errors_only=event_class == "error",
            logs_only=event_class == "log",
        )
        normalized.extend(_operational_event_payload(row) for row in log_rows)
    if include_jobs:
        job_rows = list(
            session.execute(
                select(JobQueueRecord).order_by(JobQueueRecord.created_at.desc()).limit(secondary_scan_limit)
            ).scalars()
        )
        normalized.extend(_job_operational_event_payload(row) for row in job_rows)
    if include_runtime_events:
        runtime_event_rows = list(
            session.execute(
                select(IntegrationEvent).order_by(IntegrationEvent.occurred_at.desc()).limit(secondary_scan_limit)
            ).scalars()
        )
        normalized.extend(_runtime_event_operational_event_payload(row) for row in runtime_event_rows)
    if include_requests:
        request_statement = select(RequestLog)
        if listener_id:
            request_statement = request_statement.where(RequestLog.request_json["metadata"]["listener_id"].astext == listener_id)
        if domain:
            request_statement = request_statement.where(RequestLog.domain == domain)
        if task_type:
            request_statement = request_statement.where(RequestLog.task_type == task_type)
        if traffic_origin:
            request_statement = request_statement.where(RequestLog.request_json["metadata"]["traffic_origin"].astext == traffic_origin)
        if automation_scope:
            request_statement = request_statement.where(RequestLog.request_json["metadata"]["automation_scope"].astext == automation_scope)
        if created_after_dt:
            request_statement = request_statement.where(RequestLog.created_at >= created_after_dt)
        if created_before_dt:
            request_statement = request_statement.where(RequestLog.created_at <= created_before_dt)
        if history_scope == "historical":
            request_statement = request_statement.where(RequestLog.created_at <= historical_cutoff)
        if selected_provider:
            request_statement = request_statement.where(
                RequestLog.id.in_(
                    select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_provider == selected_provider)
                )
            )
        if selected_model:
            request_statement = request_statement.where(
                RequestLog.id.in_(
                    select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_model == selected_model)
                )
            )
        if selected_pool_id:
            request_statement = request_statement.where(
                RequestLog.id.in_(
                    select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_pool_id == selected_pool_id)
                )
            )
        if selected_node_id:
            request_statement = request_statement.where(
                RequestLog.id.in_(
                    select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_node_id == selected_node_id)
                )
            )
        if prompt_template_name:
            request_statement = request_statement.where(
                RequestLog.request_json["metadata"]["prompt_template_name"].astext == prompt_template_name
            )
        if prompt_template_version is not None:
            request_statement = request_statement.where(
                RequestLog.request_json["metadata"]["prompt_template_version"].astext == str(prompt_template_version)
            )
        if prompt_template_selection_mode:
            request_statement = request_statement.where(
                RequestLog.effective_request_json["metadata"]["prompt_template_selection_mode"].astext
                == prompt_template_selection_mode
            )
        request_rows = list(
            session.execute(
                request_statement.order_by(RequestLog.created_at.desc()).limit(secondary_scan_limit)
            ).scalars()
        )
        request_ids = [row.id for row in request_rows]
        latest_routing = latest_routing_decisions_by_request(session, request_ids)
        latest_selected_responses = _latest_selected_responses_by_request(session, request_ids)
        normalized.extend(
            _request_operational_event_payload(
                {
                    **enrich_request_summary_with_routing(
                        request_summary_payload(row),
                        latest_routing.get(row.id),
                    ),
                    "latency_ms": latest_selected_responses.get(row.id, {}).get("latency_ms"),
                    "first_response_latency_ms": latest_selected_responses.get(row.id, {}).get("first_response_latency_ms"),
                    "cost_estimate": latest_selected_responses.get(row.id, {}).get("cost_estimate"),
                    "input_tokens": latest_selected_responses.get(row.id, {}).get("input_tokens"),
                    "output_tokens": latest_selected_responses.get(row.id, {}).get("output_tokens"),
                    "total_tokens": (
                        (latest_selected_responses.get(row.id, {}).get("input_tokens") or 0)
                        + (latest_selected_responses.get(row.id, {}).get("output_tokens") or 0)
                    ) if latest_selected_responses.get(row.id) is not None else None,
                }
            )
            for row in request_rows
        )
    if event_class:
        normalized = [row for row in normalized if row.get("event_class") == event_class]
    if event_source:
        normalized = [row for row in normalized if row.get("event_source") == event_source]
    if listener_id:
        normalized = [
            row for row in normalized
            if str(row.get("listener_id") or row.get("data", {}).get("listener_id") or row.get("data", {}).get("metadata", {}).get("listener_id") or "").strip().lower()
            == str(listener_id).strip().lower()
        ]
    if any([selected_provider, selected_model, selected_pool_id, selected_node_id, prompt_template_selection_mode, traffic_origin, automation_scope, domain, task_type]):
        normalized = [row for row in normalized if row.get("event_source") == "request"]
    if selected_provider:
        normalized = [row for row in normalized if str(row.get("selected_provider") or "").strip().lower() == str(selected_provider).strip().lower()]
    if selected_model:
        normalized = [row for row in normalized if str(row.get("selected_model") or "").strip().lower() == str(selected_model).strip().lower()]
    if selected_pool_id:
        normalized = [row for row in normalized if str(row.get("selected_pool_id") or "").strip().lower() == str(selected_pool_id).strip().lower()]
    if selected_node_id:
        normalized = [row for row in normalized if str(row.get("selected_node_id") or "").strip().lower() == str(selected_node_id).strip().lower()]
    if traffic_origin:
        normalized = [row for row in normalized if str(row.get("traffic_origin") or "").strip().lower() == str(traffic_origin).strip().lower()]
    if automation_scope:
        normalized = [row for row in normalized if str(row.get("automation_scope") or "").strip().lower() == str(automation_scope).strip().lower()]
    if prompt_template_name:
        normalized = [
            row
            for row in normalized
            if str(row.get("prompt_template_name") or "").strip().lower() == str(prompt_template_name).strip().lower()
        ]
    if prompt_template_version is not None:
        normalized = [row for row in normalized if row.get("prompt_template_version") == prompt_template_version]
    if prompt_template_selection_mode:
        normalized = [
            row
            for row in normalized
            if str(row.get("prompt_template_selection_mode") or "").strip().lower()
            == str(prompt_template_selection_mode).strip().lower()
        ]
    if domain:
        normalized = [row for row in normalized if str(row.get("domain") or "").strip().lower() == str(domain).strip().lower()]
    if task_type:
        normalized = [row for row in normalized if str(row.get("task_type") or "").strip().lower() == str(task_type).strip().lower()]
    if created_after_dt or created_before_dt:
        def _normalize_timestamp(value: Any) -> datetime | None:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str) and value:
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        filtered: list[dict[str, Any]] = []
        for row in normalized:
            timestamp = _normalize_timestamp(row.get("timestamp"))
            if created_after_dt and (timestamp is None or timestamp < created_after_dt):
                continue
            if created_before_dt and (timestamp is None or timestamp > created_before_dt):
                continue
            filtered.append(row)
        normalized = filtered
    if history_scope == "historical":
        filtered: list[dict[str, Any]] = []
        for row in normalized:
            timestamp = row.get("timestamp")
            if isinstance(timestamp, datetime):
                normalized_timestamp = timestamp
            elif isinstance(timestamp, str) and timestamp:
                try:
                    normalized_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    normalized_timestamp = None
            else:
                normalized_timestamp = None
            if normalized_timestamp is None or normalized_timestamp > historical_cutoff:
                continue
            filtered.append(row)
        normalized = filtered
    if promotable_only:
        normalized = [row for row in normalized if bool(row.get("promotable"))]
    reverse = sort_dir != "asc"
    normalized.sort(key=lambda row: _ops_event_sort_value(row, sort_by), reverse=reverse)
    if not paginated:
        return normalized[offset: offset + limit]
    page_items = normalized[offset: offset + limit]
    return _paged_payload(page_items, total=len(normalized), limit=limit, offset=offset)


@router.post("/api/ops/events/promote-candidate", dependencies=[Depends(require_operator_token)])
def promote_operational_event_candidate(
    request: OperationalEventPromoteRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    candidate = _promote_operational_event_to_candidate(
        session,
        event=request.event,
        domain=request.domain,
        task_type=request.task_type,
        approve_immediately=request.approve_immediately,
    )
    session.commit()
    log_record(
        get_runtime_settings(),
        level="INFO",
        component="admin.ops",
        category="audit",
        message="Operational event promoted to training candidate",
        data={
            "candidate_id": candidate.id,
            "event_source": request.event.get("event_source"),
            "event_class": request.event.get("event_class"),
            "approve_immediately": request.approve_immediately,
        },
        audit=True,
    )
    return {
        "promoted": True,
        "candidate_id": candidate.id,
        "approval_status": candidate.approval_status,
        "export_eligible": candidate.export_eligible,
    }


@router.get("/api/ops/logs/export", dependencies=[Depends(require_api_token)])
def export_operations_logs(
    limit: int = Query(default=500, le=5000),
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    listener_id: str | None = None,
    settings: Settings = Depends(get_runtime_settings),
) -> PlainTextResponse:
    rows = tail_log_records(
        settings,
        limit=limit,
        level=level,
        component=component,
        category=category,
        listener_id=listener_id,
    )
    payload = "\n".join(json.dumps(item, sort_keys=True) for item in rows)
    return PlainTextResponse(
        content=payload + ("\n" if payload else ""),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="llmproxy-logs.ndjson"'},
    )


@router.get("/api/ops/errors", dependencies=[Depends(require_api_token)])
def get_operations_errors(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    listener_id: str | None = None,
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]] | dict[str, Any]:
    rows = tail_log_records(settings, limit=limit, offset=offset, errors_only=True, listener_id=listener_id)
    if not paginated:
        return rows
    total = len(tail_log_records(settings, limit=100_000_000, offset=0, errors_only=True, listener_id=listener_id))
    return _paged_payload(rows, total=total, limit=limit, offset=offset)


@router.get("/api/ops/audit", dependencies=[Depends(require_api_token)])
def get_operations_audit(
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    listener_id: str | None = None,
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]] | dict[str, Any]:
    rows = tail_log_records(settings, limit=limit, offset=offset, audit_only=True, listener_id=listener_id)
    if not paginated:
        return rows
    total = len(tail_log_records(settings, limit=100_000_000, offset=0, audit_only=True, listener_id=listener_id))
    return _paged_payload(rows, total=total, limit=limit, offset=offset)


@router.get("/api/ops/live", dependencies=[Depends(require_api_token)])
def get_operations_live(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    live_logs = tail_log_records(settings, limit=30)
    live_errors = tail_log_records(settings, limit=20, errors_only=True)
    live_audit = tail_log_records(settings, limit=20, audit_only=True)
    return {
        "summary": build_operations_summary(session, settings=settings),
        "logs": live_logs,
        "errors": live_errors,
        "audit": live_audit,
        "events": sorted(
            [_operational_event_payload(item) for item in live_logs],
            key=lambda row: _ops_event_sort_value(row, "timestamp"),
            reverse=True,
        )[:30],
    }


@router.post("/api/ops/streaming/validate", dependencies=[Depends(require_operator_token)])
async def validate_streaming_provider(
    request: StreamingValidationRequest,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
    principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    try:
        result = await _run_frontdoor_stream_validation_suite(
            request=request,
            settings=settings,
            session=session,
            principal=principal,
        )
        log_record(
            settings,
            level="INFO",
            component="admin.streaming",
            category="audit",
            message="Front-door streaming validation executed",
            data=result,
            audit=True,
        )
        return result
    except Exception as exc:
        result = {
            "success": False,
            "listener_id": request.listener_id,
            "requested_model": request.requested_model,
            "execution_mode": request.execution_mode,
            "owner_id": request.owner_id,
            "error": str(exc),
            "validated_by": principal.role,
        }
        log_record(
            settings,
            level="ERROR",
            component="admin.streaming",
            category="error",
            message="Front-door streaming validation failed",
            data=result,
            audit=True,
        )
        return result


@router.post("/api/providers/validate", dependencies=[Depends(require_operator_token)])
async def validate_provider_runtime(
    request: ProviderValidationRequest,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    provider_registry = get_provider_registry(settings, session=session)
    provider = provider_registry.get(request.provider_key)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{request.provider_key}' is not registered.",
        )
    chat_request = ChatCompletionRequest.model_validate(
        {
            "model": getattr(provider, "model_id", "proxy-auto"),
            "messages": [{"role": "user", "content": request.prompt}],
        }
    )
    try:
        result = await provider.invoke(chat_request)
        return {
            "success": True,
            "provider_key": request.provider_key,
            "provider_family": getattr(provider, "provider_family", request.provider_key),
            "model": getattr(provider, "model_id", None),
            "result": result,
        }
    except Exception as exc:
        return {
            "success": False,
            "provider_key": request.provider_key,
            "provider_family": getattr(provider, "provider_family", request.provider_key),
            "model": getattr(provider, "model_id", None),
            "error": str(exc),
        }


@router.post("/api/replicate/predictions", dependencies=[Depends(require_operator_token)])
def enqueue_replicate_prediction(
    request: ReplicatePredictionRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = enqueue_replicate_prediction_job(
        session,
        model=request.model,
        input_payload=request.input,
        wait_for_completion=request.wait_for_completion,
    )
    session.commit()
    return {
        "queued": True,
        "job_id": job.id,
        "job_type": job.job_type,
        "model": request.model,
        "wait_for_completion": request.wait_for_completion,
    }


@router.post("/api/replicate/predictions/validate", dependencies=[Depends(require_operator_token)])
async def validate_replicate_prediction(
    request: ReplicatePredictionRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    result = await run_replicate_prediction(
        settings=settings,
        model=request.model,
        input_payload=request.input,
        wait_for_completion=request.wait_for_completion,
        include_interaction_trace=True,
    )
    return {
        "model": request.model,
        "result": result.get("result", result),
        "interaction_traces": result.get("interaction_traces", []),
        "interaction_protocols": result.get("interaction_protocols", {}),
    }


@router.get("/api/proxy/requests", dependencies=[Depends(require_api_token)])
def list_proxy_requests(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    session_id: str | None = None,
    listener_id: str | None = None,
    domain: str | None = None,
    task_type: str | None = None,
    traffic_origin: str | None = None,
    automation_scope: str | None = None,
    selected_provider: str | None = None,
    selected_model: str | None = None,
    selected_pool_id: str | None = None,
    selected_node_id: str | None = None,
    prompt_template_name: str | None = None,
    prompt_template_version: int | None = None,
    prompt_template_selection_mode: str | None = Query(default=None, pattern="^(active|challenger_canary|explicit)$"),
    created_after: str | None = None,
    created_before: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    if not isinstance(prompt_template_selection_mode, str):
        prompt_template_selection_mode = None
    statement = select(RequestLog)
    if session_id:
        statement = statement.where(RequestLog.session_id == session_id)
    if listener_id:
        statement = statement.where(RequestLog.request_json["metadata"]["listener_id"].astext == listener_id)
    if domain:
        statement = statement.where(RequestLog.domain == domain)
    if task_type:
        statement = statement.where(RequestLog.task_type == task_type)
    if traffic_origin:
        statement = statement.where(RequestLog.request_json["metadata"]["traffic_origin"].astext == traffic_origin)
    if automation_scope:
        statement = statement.where(RequestLog.request_json["metadata"]["automation_scope"].astext == automation_scope)
    if created_after:
        try:
            after_dt = datetime.fromisoformat(str(created_after).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="created_after must be an ISO timestamp.") from exc
        statement = statement.where(RequestLog.created_at >= after_dt)
    if created_before:
        try:
            before_dt = datetime.fromisoformat(str(created_before).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="created_before must be an ISO timestamp.") from exc
        statement = statement.where(RequestLog.created_at <= before_dt)
    if selected_provider:
        statement = statement.where(
            RequestLog.id.in_(
                select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_provider == selected_provider)
            )
        )
    if selected_model:
        statement = statement.where(
            RequestLog.id.in_(
                select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_model == selected_model)
            )
        )
    if selected_pool_id:
        statement = statement.where(
            RequestLog.id.in_(
                select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_pool_id == selected_pool_id)
            )
        )
    if selected_node_id:
        statement = statement.where(
            RequestLog.id.in_(
                select(RoutingDecisionRecord.request_log_id).where(RoutingDecisionRecord.selected_node_id == selected_node_id)
            )
        )
    if prompt_template_name:
        statement = statement.where(RequestLog.request_json["metadata"]["prompt_template_name"].astext == prompt_template_name)
    if prompt_template_version is not None:
        statement = statement.where(
            RequestLog.request_json["metadata"]["prompt_template_version"].astext == str(prompt_template_version)
        )
    if prompt_template_selection_mode:
        statement = statement.where(
            RequestLog.effective_request_json["metadata"]["prompt_template_selection_mode"].astext
            == prompt_template_selection_mode
        )
    total = None
    if paginated:
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    statement = statement.order_by(RequestLog.created_at.desc()).limit(limit)
    if paginated:
        statement = statement.offset(offset)
    request_rows = list(session.execute(statement).scalars())
    latest_routing = latest_routing_decisions_by_request(session, [row.id for row in request_rows])
    rows = [
        enrich_request_summary_with_routing(
            request_summary_payload(row),
            latest_routing.get(row.id),
        )
        for row in request_rows
    ]
    if not paginated:
        if traffic_origin:
            rows = [row for row in rows if str(row.get("traffic_origin", "")).lower() == traffic_origin.lower()]
        if automation_scope:
            rows = [row for row in rows if str(row.get("automation_scope", "")).lower() == automation_scope.lower()]
        if listener_id:
            rows = [row for row in rows if str(row.get("listener_id", "")).lower() == listener_id.lower()]
        if selected_provider:
            rows = [row for row in rows if str(row.get("selected_provider", "")).lower() == selected_provider.lower()]
        if selected_model:
            rows = [row for row in rows if str(row.get("selected_model", "")).lower() == selected_model.lower()]
        if selected_pool_id:
            rows = [row for row in rows if str(row.get("selected_pool_id", "")).lower() == selected_pool_id.lower()]
        if selected_node_id:
            rows = [row for row in rows if str(row.get("selected_node_id", "")).lower() == selected_node_id.lower()]
        if prompt_template_name:
            rows = [row for row in rows if str(row.get("prompt_template_name", "")).lower() == prompt_template_name.lower()]
        if prompt_template_version is not None:
            rows = [row for row in rows if row.get("prompt_template_version") == prompt_template_version]
        if prompt_template_selection_mode:
            rows = [
                row
                for row in rows
                if str(row.get("prompt_template_selection_mode", "")).lower() == prompt_template_selection_mode.lower()
            ]
        return rows
    return _paged_payload(rows, total=total or 0, limit=limit, offset=offset)


@router.get("/api/proxy/requests/{request_id}", dependencies=[Depends(require_api_token)])
def show_proxy_request(
    request_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    request = session.get(RequestLog, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
    routing_decisions = list(session.execute(select(RoutingDecisionRecord).where(RoutingDecisionRecord.request_log_id == request.id)).scalars())
    model_responses = list(
        session.execute(
            select(ModelResponse).where(ModelResponse.request_log_id == request.id).order_by(ModelResponse.created_at.asc())
        ).scalars()
    )
    judge_critiques = list(session.execute(select(JudgeCritique).where(JudgeCritique.request_log_id == request.id)).scalars())
    candidates = list(session.execute(select(TrainingCandidate).where(TrainingCandidate.request_log_id == request.id)).scalars())
    performance_samples = list(
        session.execute(select(ModelPerformanceSample).where(ModelPerformanceSample.request_log_id == request.id)).scalars()
    )
    return request_detail_payload(
        request=request,
        routing_decisions=routing_decisions,
        model_responses=model_responses,
        judge_critiques=judge_critiques,
        candidates=candidates,
        performance_samples=performance_samples,
    )


@router.get("/api/exports", dependencies=[Depends(require_api_token)])
def list_exports(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    domain: str | None = None,
    prompt_template_name: str | None = Query(default=None),
    prompt_template_version: int | None = Query(default=None),
    prompt_template_selection_mode: str | None = Query(default=None, pattern="^(active|challenger_canary|explicit)$"),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    statement = select(DatasetExport)
    if domain:
        statement = statement.where(DatasetExport.domain == domain)
    rows = list(session.execute(statement.order_by(DatasetExport.created_at.desc())).scalars())
    payload = [dataset_export_payload(row) for row in rows]
    if prompt_template_name:
        normalized_name = prompt_template_name.strip().lower()
        payload = [
            row
            for row in payload
            if str((row.get("interaction_filters") or {}).get("prompt_template_name") or "").strip().lower() == normalized_name
        ]
    if prompt_template_version is not None:
        payload = [
            row
            for row in payload
            if (row.get("interaction_filters") or {}).get("prompt_template_version") == prompt_template_version
        ]
    if prompt_template_selection_mode:
        normalized_mode = prompt_template_selection_mode.strip().lower()
        payload = [
            row
            for row in payload
            if (
                str((row.get("interaction_filters") or {}).get("prompt_template_selection_mode") or "").strip().lower() == normalized_mode
                or normalized_mode in {str(key).strip().lower() for key in (row.get("prompt_rollout_mode_counts") or {}).keys()}
            )
        ]
    if not paginated:
        return payload
    items, total = _slice_items(payload, limit=limit, offset=offset)
    return _paged_payload(items, total=total, limit=limit, offset=offset)


@router.get("/api/datasets/imports", dependencies=[Depends(require_api_token)])
def list_dataset_imports(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    statement = select(DatasetImport)
    total = None
    if paginated:
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    rows = list(
        session.execute(
            statement.order_by(DatasetImport.created_at.desc()).limit(limit).offset(offset if paginated else 0)
        ).scalars()
    )
    payload = [dataset_import_payload(row) for row in rows]
    if not paginated:
        return payload
    return _paged_payload(payload, total=total or 0, limit=limit, offset=offset)


@router.get("/api/datasets/versions", dependencies=[Depends(require_api_token)])
def list_dataset_versions(
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    domain: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    statement = select(DatasetVersion)
    if domain:
        statement = statement.where(DatasetVersion.domain == domain)
    total = None
    if paginated:
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    rows = list(
        session.execute(
            statement.order_by(DatasetVersion.created_at.desc()).limit(limit).offset(offset if paginated else 0)
        ).scalars()
    )
    payload = [dataset_version_payload(row) for row in rows]
    if not paginated:
        return payload
    return _paged_payload(payload, total=total or 0, limit=limit, offset=offset)


@router.get("/api/training/runs/{training_run_id}", dependencies=[Depends(require_api_token)])
def show_training_run(
    training_run_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(TrainingRun, training_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found.")
    return {
        **training_run_payload(run),
        "pipeline_traffic": build_learning_pipeline_traffic_summary(session, owner_id=run.id),
    }


@router.get("/api/training/runtime-status", dependencies=[Depends(require_api_token)])
def show_training_runtime_status() -> dict[str, Any]:
    status_payload = get_reported_training_runtime_status()
    if status_payload is None:
        return {"available": False, "detail": "No training-worker runtime status has been reported yet."}
    return {"available": True, **status_payload.model_dump(mode="json")}


@router.get("/api/training/studio-status", dependencies=[Depends(require_api_token)])
def show_training_studio_status(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return get_training_studio_status(settings).model_dump(mode="json")


@router.get("/api/evaluation/runs/{evaluation_run_id}", dependencies=[Depends(require_api_token)])
def show_evaluation_run(
    evaluation_run_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(EvaluationRun, evaluation_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found.")
    return {
        **evaluation_run_payload(run),
        "pipeline_traffic": build_learning_pipeline_traffic_summary(session, owner_id=run.id),
    }


@router.get("/api/jobs", dependencies=[Depends(require_api_token)])
def list_jobs(
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    statement = select(JobQueueRecord)
    if status_filter:
        statement = statement.where(JobQueueRecord.status == status_filter)
    if job_type:
        statement = statement.where(JobQueueRecord.job_type == job_type)
    total = None
    if paginated:
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    statement = statement.order_by(JobQueueRecord.created_at.desc()).limit(limit)
    if paginated:
        statement = statement.offset(offset)
    rows = list(session.execute(statement).scalars())
    payload = [job_payload(row) for row in rows]
    if not paginated:
        return payload
    return _paged_payload(payload, total=total or 0, limit=limit, offset=offset)


@router.get("/api/jobs/{job_id}", dependencies=[Depends(require_api_token)])
def show_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.get(JobQueueRecord, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job_payload(job)


@router.post("/api/jobs/{job_id}/retry", dependencies=[Depends(require_operator_token)])
def retry_job(
    job_id: str,
    request: JobRetryRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = session.get(JobQueueRecord, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    job.status = "pending"
    job.claimed_at = None
    job.completed_at = None
    job.last_error = None
    if request.reset_attempts:
        job.attempts = 0
    if request.available_now:
        job.available_at = datetime.now(timezone.utc)
    session.commit()
    log_record(
        settings=get_runtime_settings(),
        level="INFO",
        component="admin.jobs",
        category="audit",
        message="Job retried",
        data={"job_id": job.id, "job_type": job.job_type, "reset_attempts": request.reset_attempts, "available_now": request.available_now},
        audit=True,
    )
    return {"retried": True, "job": job_payload(job)}


@router.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(require_operator_token)])
def cancel_job(
    job_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    job = session.get(JobQueueRecord, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    job.status = "cancelled"
    job.completed_at = datetime.now(timezone.utc)
    session.commit()
    log_record(
        settings=get_runtime_settings(),
        level="INFO",
        component="admin.jobs",
        category="audit",
        message="Job cancelled",
        data={"job_id": job.id, "job_type": job.job_type},
        audit=True,
    )
    return {"cancelled": True, "job": job_payload(job)}


@router.post("/api/jobs/run-once", dependencies=[Depends(require_operator_token)])
def run_jobs_once(_principal: AuthPrincipal = Depends(require_operator_token)) -> dict[str, Any]:
    processed = run_worker_iteration()
    log_record(
        settings=get_runtime_settings(),
        level="INFO",
        component="admin.jobs",
        category="audit",
        message="Worker iteration triggered from admin console",
        data={"processed": processed},
        audit=True,
    )
    return {"processed": processed}


@router.get("/api/events", dependencies=[Depends(require_api_token)])
def list_events(
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    paginated: bool = False,
    event_type: str | None = None,
    unprocessed: bool = False,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]] | dict[str, Any]:
    statement = select(IntegrationEvent)
    if event_type:
        statement = statement.where(IntegrationEvent.event_type == event_type)
    if unprocessed:
        statement = statement.where(IntegrationEvent.processed_at.is_(None))
    total = None
    if paginated:
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    statement = statement.order_by(IntegrationEvent.occurred_at.desc()).limit(limit)
    if paginated:
        statement = statement.offset(offset)
    rows = list(session.execute(statement).scalars())
    payload = [event_payload(row) for row in rows]
    if not paginated:
        return payload
    return _paged_payload(payload, total=total or 0, limit=limit, offset=offset)


@router.get("/api/events/{event_id}", dependencies=[Depends(require_api_token)])
def show_event(event_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    event = session.get(IntegrationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return event_payload(event)


@router.post("/api/events/process", dependencies=[Depends(require_operator_token)])
def process_events(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    response = process_pending_events(session, settings=settings)
    session.commit()
    log_record(
        settings,
        level="INFO",
        component="admin.events",
        category="audit",
        message="Pending events processed from admin console",
        data=response.model_dump(mode="json"),
        audit=True,
    )
    return response.model_dump(mode="json")


@router.post("/api/events/{event_id}/replay", dependencies=[Depends(require_operator_token)])
def replay_event(
    event_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    event = session.get(IntegrationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    event.processed_at = None
    session.flush()
    response = process_pending_events(session, settings=settings)
    session.commit()
    log_record(
        settings,
        level="INFO",
        component="admin.events",
        category="audit",
        message="Event replayed from admin console",
        data={"event_id": event.id, "event_type": event.event_type, **response.model_dump(mode="json")},
        audit=True,
    )
    return {
        "replayed": True,
        "event_id": event.id,
        "event_type": event.event_type,
        "processed_count": response.processed_count,
        "imported_count": response.imported_count,
    }


@router.post("/api/scheduler/run-once", dependencies=[Depends(require_operator_token)])
def run_scheduler_once(_principal: AuthPrincipal = Depends(require_operator_token)) -> dict[str, Any]:
    run_scheduler_iteration()
    log_record(
        settings=get_runtime_settings(),
        level="INFO",
        component="admin.scheduler",
        category="audit",
        message="Scheduler iteration triggered from admin console",
        data={"scheduled": True},
        audit=True,
    )
    return {"scheduled": True}
