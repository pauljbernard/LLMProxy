"""Inventory, validation, and invocation helpers for generic REST endpoints."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import HTTPException, status

from app.config import Settings
from app.services.interaction_traces import build_http_interaction_trace, summarize_interaction_trace_protocols


def _endpoint_config(settings: Settings, endpoint_name: str) -> dict[str, Any]:
    raw = getattr(settings, "llmproxy_rest_endpoints", {}).get(endpoint_name)
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="REST endpoint not found.")
    return raw


def _endpoint_base_url(config: dict[str, Any]) -> str:
    return str(config.get("endpoint") or config.get("base_url") or "").strip()


def _endpoint_url(config: dict[str, Any], *, path_key: str, default_path: str = "") -> str:
    base = _endpoint_base_url(config)
    if not base:
        return ""
    path = str(config.get(path_key) or default_path).strip()
    if not path:
        return base
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _endpoint_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    auth_mode = str(config.get("auth_mode") or ("bearer" if config.get("token") else "none"))
    token = str(config.get("token") or "").strip()
    if auth_mode == "bearer" and token:
        headers["Authorization"] = f"Bearer {token}"
    configured_headers = config.get("headers")
    if isinstance(configured_headers, dict):
        for key, value in configured_headers.items():
            if key and value is not None:
                headers[str(key)] = str(value)
    return headers


def _endpoint_payload(endpoint_name: str, config: dict[str, Any]) -> dict[str, Any]:
    base_url = _endpoint_base_url(config)
    labels = config.get("labels")
    notes = config.get("notes")
    headers = config.get("headers")
    auth_mode = str(config.get("auth_mode") or ("bearer" if config.get("token") else "none"))
    return {
        "endpoint_name": endpoint_name,
        "label": str(config.get("label") or endpoint_name),
        "protocol": "rest",
        "transport": str(config.get("transport") or "http"),
        "endpoint": base_url,
        "validate_url": _endpoint_url(config, path_key="validation_path", default_path=""),
        "invoke_url": _endpoint_url(config, path_key="invoke_path", default_path=""),
        "configured": bool(base_url),
        "auth_mode": auth_mode,
        "default_method": str(config.get("method") or "POST").upper(),
        "validation_method": str(config.get("validation_method") or "GET").upper(),
        "timeout_seconds": float(config.get("timeout_seconds", 10.0)),
        "header_count": len(headers) if isinstance(headers, dict) else 0,
        "labels": labels if isinstance(labels, list) else [],
        "notes": notes if isinstance(notes, list) else [],
    }


async def list_rest_endpoints(settings: Settings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for endpoint_name, raw in getattr(settings, "llmproxy_rest_endpoints", {}).items():
        config = raw if isinstance(raw, dict) else {}
        rows.append(_endpoint_payload(endpoint_name, config))
    rows.sort(key=lambda row: str(row.get("label") or row.get("endpoint_name") or ""))
    return rows


async def inspect_rest_endpoint(settings: Settings, endpoint_name: str) -> dict[str, Any]:
    config = _endpoint_config(settings, endpoint_name)
    payload = _endpoint_payload(endpoint_name, config)
    if not payload["configured"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="REST endpoint is missing an endpoint.")

    method = str(payload["validation_method"] or "GET").upper()
    headers = _endpoint_headers(config)
    url = str(payload["validate_url"] or payload["endpoint"])
    request_payload = config.get("validation_payload")
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=payload["timeout_seconds"], follow_redirects=True) as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=request_payload if isinstance(request_payload, dict) else None)
            else:
                body = request_payload if isinstance(request_payload, dict) else None
                response = await client.request(method, url, headers={**headers, "Content-Type": "application/json"}, json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"REST endpoint validation failed: {exc}",
        ) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)
    content_type = response.headers.get("content-type", "")
    body: dict[str, Any] | list[Any] | None = None
    parse_error: str | None = None
    text_body: str | None = None
    try:
        body = response.json()
    except ValueError:
        parse_error = "Validation endpoint did not return valid JSON."
        text_body = response.text

    interaction_traces = [
        build_http_interaction_trace(
            protocol="rest",
            operation="validate_endpoint",
            method=method,
            endpoint=url,
            success=response.is_success,
            status_code=response.status_code,
            latency_ms=latency_ms,
            source="llmproxy.integrations",
            request_payload=request_payload if isinstance(request_payload, dict) else {},
            response_payload=body if body is not None else {"text": text_body, "parse_error": parse_error},
        )
    ]
    return {
        **payload,
        "validated": response.is_success,
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "content_type": content_type,
        "result": body if body is not None else text_body,
        "parse_error": parse_error,
        "interaction_traces": interaction_traces,
        "interaction_protocols": summarize_interaction_trace_protocols(interaction_traces),
    }


async def invoke_rest_endpoint(
    settings: Settings,
    endpoint_name: str,
    *,
    method: str | None = None,
    path: str | None = None,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    config = _endpoint_config(settings, endpoint_name)
    payload = _endpoint_payload(endpoint_name, config)
    if not payload["configured"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="REST endpoint is missing an endpoint.")

    resolved_method = str(method or payload["default_method"] or "POST").upper()
    resolved_url = (
        urljoin(str(payload["endpoint"]).rstrip("/") + "/", str(path).lstrip("/"))
        if str(path or "").strip()
        else str(payload["invoke_url"] or payload["endpoint"])
    )
    headers = _endpoint_headers(config)
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=payload["timeout_seconds"], follow_redirects=True) as client:
            if resolved_method == "GET":
                response = await client.get(resolved_url, headers=headers, params=input_payload or None)
            else:
                response = await client.request(
                    resolved_method,
                    resolved_url,
                    headers={**headers, "Content-Type": "application/json"},
                    json=input_payload or {},
                )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"REST endpoint invocation failed: {exc}",
        ) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)
    content_type = response.headers.get("content-type", "")
    body: dict[str, Any] | list[Any] | None = None
    parse_error: str | None = None
    text_body: str | None = None
    try:
        body = response.json()
    except ValueError:
        parse_error = "Invocation endpoint did not return valid JSON."
        text_body = response.text

    interaction_traces = [
        build_http_interaction_trace(
            protocol="rest",
            operation="invoke_endpoint",
            method=resolved_method,
            endpoint=resolved_url,
            success=response.is_success,
            status_code=response.status_code,
            latency_ms=latency_ms,
            source="llmproxy.integrations",
            request_payload=input_payload or {},
            response_payload=body if body is not None else {"text": text_body, "parse_error": parse_error},
        )
    ]
    return {
        **payload,
        "invoked": True,
        "invoked_method": resolved_method,
        "invoked_path": str(path or "").strip() or None,
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "content_type": content_type,
        "result": body if body is not None else text_body,
        "parse_error": parse_error,
        "interaction_traces": interaction_traces,
        "interaction_protocols": summarize_interaction_trace_protocols(interaction_traces),
    }
