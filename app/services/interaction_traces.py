"""Normalized interaction-trace builders for cross-protocol learning data."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from app.db.models import ModelResponse, RequestLog, RoutingDecisionRecord
from app.services.learning_pipeline import (
    request_automation_owner_id,
    request_automation_scope,
    request_metadata_payload,
    request_traffic_origin,
    request_virtual_key_id,
    request_virtual_key_role,
)


def _request_payload(request: RequestLog | dict[str, Any]) -> dict[str, Any]:
    if isinstance(request, RequestLog):
        return request.request_json or {}
    return request if isinstance(request, dict) else {}


def _response_payload(response: ModelResponse | dict[str, Any]) -> dict[str, Any]:
    if isinstance(response, ModelResponse):
        return response.response_json or {}
    return response if isinstance(response, dict) else {}


def _routing_payload(routing: RoutingDecisionRecord | dict[str, Any] | None) -> dict[str, Any]:
    if routing is None:
        return {}
    if isinstance(routing, RoutingDecisionRecord):
        return {
            "selected_mode": routing.selected_mode,
            "selected_pool_id": routing.selected_pool_id,
            "selected_node_id": routing.selected_node_id,
            "selected_node_role": routing.selected_node_role,
            "selected_balancing_strategy": routing.selected_balancing_strategy,
            "selected_affinity_key": routing.selected_affinity_key,
        }
    if isinstance(routing, dict):
        return {
            "selected_mode": routing.get("selected_mode"),
            "selected_pool_id": routing.get("selected_pool_id"),
            "selected_node_id": routing.get("selected_node_id"),
            "selected_node_role": routing.get("selected_node_role"),
            "selected_balancing_strategy": routing.get("selected_balancing_strategy"),
            "selected_affinity_key": routing.get("selected_affinity_key"),
        }
    return {}


def _trace_context(request: RequestLog | dict[str, Any]) -> dict[str, Any]:
    payload = _request_payload(request)
    metadata = request_metadata_payload(request)
    return {
        "session_id": payload.get("metadata", {}).get("session_id") or getattr(request, "session_id", None),
        "traffic_origin": request_traffic_origin(request),
        "automation_scope": request_automation_scope(request),
        "automation_owner_id": request_automation_owner_id(request),
        "virtual_key_id": request_virtual_key_id(request),
        "virtual_key_role": request_virtual_key_role(request),
        "request_metadata": metadata,
    }


def build_http_interaction_trace(
    *,
    protocol: str,
    operation: str,
    method: str,
    endpoint: str,
    success: bool,
    status_code: int | None = None,
    latency_ms: int | None = None,
    source: str = "llmproxy",
    request_id: str | None = None,
    parent_trace_id: str | None = None,
    request_payload: dict[str, Any] | None = None,
    response_payload: Any = None,
    peer: str | None = None,
    capability: str | None = None,
) -> dict[str, Any]:
    endpoint_label = endpoint or "endpoint"
    method_label = (method or "HTTP").upper()
    target_label = peer or endpoint_label
    operation_label = operation or "request"
    return {
        "trace_id": f"trace_{protocol}_{method_label.lower()}_{target_label}_{operation_label}",
        "protocol": protocol,
        "operation": operation_label,
        "source": source,
        "request_id": request_id,
        "parent_trace_id": parent_trace_id,
        "success": bool(success),
        "peer": peer,
        "capability": capability,
        "method": method_label,
        "endpoint": endpoint,
        "request_payload": request_payload or {},
        "response_payload": response_payload,
        "metrics": {
            "latency_ms": latency_ms,
            "status_code": status_code,
        },
    }


def build_llm_interaction_trace(
    *,
    request: RequestLog | dict[str, Any],
    response: ModelResponse | dict[str, Any],
    routing: RoutingDecisionRecord | dict[str, Any] | None = None,
    request_id: str | None = None,
    response_id: str | None = None,
    output_content: str | None = None,
) -> dict[str, Any]:
    request_payload = _request_payload(request)
    response_payload = _response_payload(response)
    context = _trace_context(request)
    routing_payload = _routing_payload(routing)
    resolved_request_id = request_id or getattr(request, "id", None) or str(request_payload.get("id") or "")
    resolved_response_id = response_id or getattr(response, "id", None) or str(response_payload.get("id") or "")
    if output_content is None and isinstance(response_payload, dict):
        output_content = (
            response_payload.get("content")
            or response_payload.get("output_text")
            or response_payload.get("text")
        )
    return {
        "trace_id": f"trace_llm_{resolved_response_id or resolved_request_id}",
        "protocol": "llm",
        "operation": "chat_completion",
        "source": "llmproxy",
        "request_id": resolved_request_id or None,
        "response_id": resolved_response_id or None,
        "session_id": context["session_id"],
        "success": True,
        "provider": getattr(response, "provider", None) or response_payload.get("provider"),
        "provider_family": getattr(response, "provider_family", None) or response_payload.get("provider_family"),
        "model": getattr(response, "model", None) or response_payload.get("model"),
        "response_role": getattr(response, "response_role", None) or response_payload.get("response_role"),
        "traffic_origin": context["traffic_origin"],
        "automation_scope": context["automation_scope"],
        "automation_owner_id": context["automation_owner_id"],
        "virtual_key_id": context["virtual_key_id"],
        "virtual_key_role": context["virtual_key_role"],
        "routing": routing_payload,
        "request_payload": {
            "requested_model": request_payload.get("model") or getattr(request, "requested_model", None),
            "messages": request_payload.get("messages", []),
            "tools": request_payload.get("tools", []),
            "metadata": context["request_metadata"],
        },
        "response_payload": {
            "content": output_content,
            "finish_reason": getattr(response, "finish_reason", None) or response_payload.get("finish_reason"),
            "raw_response": response_payload,
        },
        "metrics": {
            "latency_ms": getattr(response, "latency_ms", None) or response_payload.get("latency_ms"),
            "input_tokens": getattr(response, "input_tokens", None) or response_payload.get("input_tokens"),
            "output_tokens": getattr(response, "output_tokens", None) or response_payload.get("output_tokens"),
            "cost_estimate": float(getattr(response, "cost_estimate", Decimal("0")) or response_payload.get("cost_estimate") or 0),
        },
        "created_at": getattr(response, "created_at", None) or getattr(request, "created_at", None),
    }


def extract_mcp_interaction_traces(
    *,
    request: RequestLog | dict[str, Any],
    response: ModelResponse | dict[str, Any],
    parent_trace_id: str | None = None,
    request_id: str | None = None,
) -> list[dict[str, Any]]:
    payload = _response_payload(response)
    raw_traces = payload.get("mcp_trace")
    if not isinstance(raw_traces, list):
        return []
    context = _trace_context(request)
    resolved_request_id = request_id or getattr(request, "id", None) or str(_request_payload(request).get("id") or "")
    traces: list[dict[str, Any]] = []
    for index, item in enumerate(raw_traces):
        if not isinstance(item, dict):
            continue
        traces.append(
            {
                "trace_id": f"trace_mcp_{resolved_request_id}_{index}",
                "protocol": "mcp",
                "operation": "tool_call",
                "source": "llmproxy",
                "request_id": resolved_request_id or None,
                "parent_trace_id": parent_trace_id,
                "session_id": context["session_id"],
                "success": item.get("error") in (None, "", False),
                "server": item.get("server"),
                "tool_name": item.get("tool_name"),
                "traffic_origin": context["traffic_origin"],
                "automation_scope": context["automation_scope"],
                "automation_owner_id": context["automation_owner_id"],
                "virtual_key_id": context["virtual_key_id"],
                "virtual_key_role": context["virtual_key_role"],
                "request_payload": item.get("arguments") if isinstance(item.get("arguments"), dict) else {"arguments": item.get("arguments")},
                "response_payload": item.get("result"),
                "metrics": {
                    "latency_ms": item.get("latency_ms"),
                },
            }
        )
    return traces


def build_request_interaction_traces(
    *,
    request: RequestLog,
    routing_decisions: list[RoutingDecisionRecord],
    model_responses: list[ModelResponse],
) -> list[dict[str, Any]]:
    routing_by_id = {item.request_log_id: item for item in routing_decisions}
    traces: list[dict[str, Any]] = []
    for response in model_responses:
        routing = routing_by_id.get(response.request_log_id)
        llm_trace = build_llm_interaction_trace(
            request=request,
            response=response,
            routing=routing,
        )
        traces.append(llm_trace)
        traces.extend(
            extract_mcp_interaction_traces(
                request=request,
                response=response,
                parent_trace_id=llm_trace["trace_id"],
                request_id=request.id,
            )
        )
    return traces


def summarize_interaction_trace_protocols(traces: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(item.get("protocol") or "unknown") for item in traces if isinstance(item, dict))
    return dict(sorted(counts.items()))
