"""Administrative operator UI and API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import (
    AuthPrincipal,
    get_runtime_settings,
    get_session,
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
from app.config import Settings
from app.db.models import DatasetExport, DatasetImport, DatasetVersion, EvaluationRun, IntegrationEvent, JobQueueRecord, JudgeCritique, ModelPerformanceSample, ModelResponse, PromptTemplate, RequestLog, RoutingDecisionRecord, TrainingCandidate, TrainingRun
from app.integration.outbox import process_pending_events
from app.integration.jobs import enqueue_replicate_prediction_job
from app.operator_payloads import (
    dataset_export_payload,
    dataset_import_payload,
    dataset_version_payload,
    evaluation_run_payload,
    event_payload,
    job_payload,
    request_detail_payload,
    request_summary_payload,
    settings_payload,
    training_run_payload,
)
from app.proxy.classifier import classify_request
from app.proxy.router import select_route
from app.registry.model_registry import get_provider_registry, list_provider_capabilities, resolve_provider
from app.runtime import run_scheduler_iteration, run_worker_iteration
from app.services.cost import pricing_catalog
from app.services.mcp_gateway import _list_mcp_tools, inspect_mcp_server
from app.services.observability import build_operations_summary, log_record, tail_log_records
from app.services.prompt_templates import (
    PromptTemplateCreateInput,
    PromptTemplateError,
    create_prompt_template,
    diff_prompt_templates,
    get_prompt_template,
    list_prompt_templates,
    prompt_template_payload,
    render_prompt_template,
)
from app.services.replicate_predictions import run_replicate_prediction
from app.schemas.chat import ChatCompletionRequest

router = APIRouter(prefix="/admin", tags=["admin"])

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static" / "admin"


class ConfigSetRequest(BaseModel):
    key: str
    value: str
    env_file: str = ".env.local"


class JobRetryRequest(BaseModel):
    reset_attempts: bool = False
    available_now: bool = False


class StreamingValidationRequest(BaseModel):
    provider_key: str | None = None
    prompt: str = "Say hello briefly."
    requested_model: str = "proxy-auto"
    domain_hint: str = "general"
    task_type_hint: str = "analysis"
    max_chunks: int = 12


class ProviderValidationRequest(BaseModel):
    provider_key: str
    prompt: str = "Say hello briefly."


class ReplicatePredictionRequest(BaseModel):
    model: str
    input: dict[str, object]
    wait_for_completion: bool = True


class RoutingSettingsUpdateRequest(BaseModel):
    routing_strategy: str
    frontier_default_entries: list[dict[str, object]]
    env_file: str = ".env.local"


class PromptTemplateAdminCreateRequest(BaseModel):
    name: str
    template_text: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)
    model_override: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class PromptTemplateAdminRenderRequest(BaseModel):
    version: int | None = None
    variables: dict[str, object] = Field(default_factory=dict)


class RoutePreviewRequest(BaseModel):
    model: str = "proxy-auto"
    temperature: float = 0.2
    max_tokens: int = 1024
    messages: list[dict[str, object]]
    session_id: str
    domain_hint: str | None = None
    task_type_hint: str | None = None
    region_hint: str | None = None
    route_tags: list[str] = Field(default_factory=list)


def _write_env_value(env_file: Path, key: str, value: str) -> None:
    lines: list[str] = []
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


def _observability_payload(settings: Settings) -> dict[str, Any]:
    prometheus_path = "/metrics/prometheus"
    return {
        "prometheus": {
            "enabled": settings.llmproxy_prometheus_metrics_enabled,
            "path": prometheus_path,
            "scrape_config": {
                "job_name": "llmproxy",
                "metrics_path": prometheus_path,
                "static_configs": [{"targets": [f"127.0.0.1:{settings.llmproxy_api_port}"]}],
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


@router.get("/api/mcp/servers", dependencies=[Depends(require_api_token)])
async def get_mcp_servers(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    rows = await _mcp_server_payloads(settings)
    return {
        "server_count": len(rows),
        "tool_count": sum(int(item.get("tool_count", 0)) for item in rows),
        "servers": rows,
    }


@router.get("/api/providers/guides", dependencies=[Depends(require_api_token)])
def get_provider_guides(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    guides = _provider_guides(settings)
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


@router.get("/api/guardrails/settings", dependencies=[Depends(require_operator_token)])
def get_guardrails_settings(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return _guardrails_payload(settings)


@router.get("/api/prompts", dependencies=[Depends(require_api_token)])
def get_prompt_templates(
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return [prompt_template_payload(item) for item in list_prompt_templates(session)]


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
            metadata=request.metadata,
        ),
    )
    return prompt_template_payload(record)


@router.get("/api/prompts/{name}", dependencies=[Depends(require_api_token)])
def get_prompt_template_api(
    name: str,
    version: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    record = get_prompt_template(session, name=name, version=version)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt template not found.")
    return prompt_template_payload(record)


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
    payload["rendered_text"] = rendered
    payload["render_variables"] = request.variables
    return payload


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


@router.get("/api/auth/virtual-keys", response_model=list[VirtualKeyView], dependencies=[Depends(require_operator_token)])
def list_virtual_keys(
    session: Session = Depends(get_session),
) -> list[VirtualKeyView]:
    rows = list_virtual_key_records(session)
    return [VirtualKeyView.model_validate(virtual_key_payload(item)) for item in rows]


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


@router.get("/api/ops/logs", dependencies=[Depends(require_api_token)])
def get_operations_logs(
    limit: int = Query(default=100, le=500),
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]]:
    return tail_log_records(
        settings,
        limit=limit,
        level=level,
        component=component,
        category=category,
    )


@router.get("/api/ops/logs/export", dependencies=[Depends(require_api_token)])
def export_operations_logs(
    limit: int = Query(default=500, le=5000),
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    settings: Settings = Depends(get_runtime_settings),
) -> PlainTextResponse:
    rows = tail_log_records(
        settings,
        limit=limit,
        level=level,
        component=component,
        category=category,
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
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]]:
    return tail_log_records(settings, limit=limit, errors_only=True)


@router.get("/api/ops/audit", dependencies=[Depends(require_api_token)])
def get_operations_audit(
    limit: int = Query(default=100, le=500),
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]]:
    return tail_log_records(settings, limit=limit, audit_only=True)


@router.get("/api/ops/live", dependencies=[Depends(require_api_token)])
def get_operations_live(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return {
        "summary": build_operations_summary(session, settings=settings),
        "logs": tail_log_records(settings, limit=30),
        "errors": tail_log_records(settings, limit=20, errors_only=True),
        "audit": tail_log_records(settings, limit=20, audit_only=True),
    }


@router.post("/api/ops/streaming/validate", dependencies=[Depends(require_operator_token)])
async def validate_streaming_provider(
    request: StreamingValidationRequest,
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
    principal: AuthPrincipal = Depends(require_operator_token),
) -> dict[str, Any]:
    provider_registry = get_provider_registry(settings, session=session)
    provider_order = (
        [request.provider_key] if request.provider_key else ["openai", "anthropic", "google", "xai", "azure_openai", "bedrock"]
    )
    selected_key = None
    selected_provider = None
    for provider_key in provider_order:
        provider = provider_registry.get(provider_key)
        if provider is None or not getattr(provider, "supports_streaming", False):
            continue
        if request.provider_key:
            selected_key = provider_key
            selected_provider = provider
            break
        configured = settings_payload(settings)["provider_configuration"].get(provider_key, False)
        if configured:
            selected_key = provider_key
            selected_provider = provider
            break
    if selected_provider is None or selected_key is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No configured streaming frontier provider is available.")

    chat_request = ChatCompletionRequest.model_validate(
        {
            "model": request.requested_model if request.requested_model != "proxy-auto" else getattr(selected_provider, "model_id", "proxy-auto"),
            "stream": True,
            "messages": [{"role": "user", "content": request.prompt}],
            "metadata": {
                "session_id": "admin_stream_validation",
                "domain_hint": request.domain_hint,
                "task_type_hint": request.task_type_hint,
            },
        }
    )
    chunks: list[str] = []
    finish_reason = None
    input_tokens = 0
    output_tokens = 0
    try:
        async for chunk in selected_provider.stream_chat(chat_request):
            text_delta = str(chunk.get("delta", ""))
            if text_delta and len(chunks) < request.max_chunks:
                chunks.append(text_delta)
            input_tokens = max(input_tokens, int(chunk.get("input_tokens", 0)))
            output_tokens = max(output_tokens, int(chunk.get("output_tokens", 0)))
            if chunk.get("finish_reason"):
                finish_reason = str(chunk["finish_reason"])
            if len(chunks) >= request.max_chunks and finish_reason:
                break
        result = {
            "success": True,
            "provider_key": selected_key,
            "provider_family": getattr(selected_provider, "provider_family", selected_key),
            "model": getattr(selected_provider, "model_id", None),
            "chunk_preview": chunks,
            "preview_text": "".join(chunks),
            "finish_reason": finish_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "validated_by": principal.role,
        }
        log_record(
            settings,
            level="INFO",
            component="admin.streaming",
            category="audit",
            message="Streaming provider validation executed",
            data=result,
            audit=True,
        )
        return result
    except Exception as exc:
        result = {
            "success": False,
            "provider_key": selected_key,
            "provider_family": getattr(selected_provider, "provider_family", selected_key),
            "model": getattr(selected_provider, "model_id", None),
            "error": str(exc),
            "validated_by": principal.role,
        }
        log_record(
            settings,
            level="ERROR",
            component="admin.streaming",
            category="error",
            message="Streaming provider validation failed",
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
    )
    return {
        "model": request.model,
        "result": result,
    }


@router.get("/api/proxy/requests", dependencies=[Depends(require_api_token)])
def list_proxy_requests(
    limit: int = Query(default=20, le=200),
    session_id: str | None = None,
    domain: str | None = None,
    task_type: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit)
    if session_id:
        statement = statement.where(RequestLog.session_id == session_id)
    if domain:
        statement = statement.where(RequestLog.domain == domain)
    if task_type:
        statement = statement.where(RequestLog.task_type == task_type)
    rows = list(session.execute(statement).scalars())
    return [request_summary_payload(row) for row in rows]


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
    domain: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(DatasetExport).order_by(DatasetExport.created_at.desc()).limit(limit)
    if domain:
        statement = statement.where(DatasetExport.domain == domain)
    rows = list(session.execute(statement).scalars())
    return [dataset_export_payload(row) for row in rows]


@router.get("/api/datasets/imports", dependencies=[Depends(require_api_token)])
def list_dataset_imports(
    limit: int = Query(default=20, le=200),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = list(session.execute(select(DatasetImport).order_by(DatasetImport.created_at.desc()).limit(limit)).scalars())
    return [dataset_import_payload(row) for row in rows]


@router.get("/api/datasets/versions", dependencies=[Depends(require_api_token)])
def list_dataset_versions(
    limit: int = Query(default=20, le=200),
    domain: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(DatasetVersion).order_by(DatasetVersion.created_at.desc()).limit(limit)
    if domain:
        statement = statement.where(DatasetVersion.domain == domain)
    rows = list(session.execute(statement).scalars())
    return [dataset_version_payload(row) for row in rows]


@router.get("/api/training/runs/{training_run_id}", dependencies=[Depends(require_api_token)])
def show_training_run(
    training_run_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(TrainingRun, training_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found.")
    return training_run_payload(run)


@router.get("/api/evaluation/runs/{evaluation_run_id}", dependencies=[Depends(require_api_token)])
def show_evaluation_run(
    evaluation_run_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(EvaluationRun, evaluation_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found.")
    return evaluation_run_payload(run)


@router.get("/api/jobs", dependencies=[Depends(require_api_token)])
def list_jobs(
    limit: int = Query(default=50, le=500),
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = None,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(JobQueueRecord).order_by(JobQueueRecord.created_at.desc()).limit(limit)
    if status_filter:
        statement = statement.where(JobQueueRecord.status == status_filter)
    if job_type:
        statement = statement.where(JobQueueRecord.job_type == job_type)
    rows = list(session.execute(statement).scalars())
    return [job_payload(row) for row in rows]


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
    event_type: str | None = None,
    unprocessed: bool = False,
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    statement = select(IntegrationEvent).order_by(IntegrationEvent.occurred_at.desc()).limit(limit)
    if event_type:
        statement = statement.where(IntegrationEvent.event_type == event_type)
    if unprocessed:
        statement = statement.where(IntegrationEvent.processed_at.is_(None))
    rows = list(session.execute(statement).scalars())
    return [event_payload(row) for row in rows]


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
