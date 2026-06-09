"""Inventory and validation helpers for A2A peers."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import HTTPException, status

from app.config import Settings
from app.services.interaction_traces import build_http_interaction_trace, summarize_interaction_trace_protocols


def _peer_config(settings: Settings, peer_name: str) -> dict[str, Any]:
    raw = getattr(settings, "llmproxy_a2a_peers", {}).get(peer_name)
    if not isinstance(raw, dict):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="A2A peer not found.")
    return raw


def _peer_endpoint(config: dict[str, Any]) -> str:
    return str(config.get("endpoint") or config.get("base_url") or "").strip()


def _peer_discovery_url(config: dict[str, Any]) -> str:
    endpoint = _peer_endpoint(config)
    if not endpoint:
        return ""
    discovery_path = str(config.get("discovery_path") or "/.well-known/agent.json").strip() or "/.well-known/agent.json"
    return urljoin(endpoint.rstrip("/") + "/", discovery_path.lstrip("/"))


def _peer_invoke_url(config: dict[str, Any]) -> str:
    endpoint = _peer_endpoint(config)
    if not endpoint:
        return ""
    invoke_path = str(config.get("invoke_path") or "/invoke").strip() or "/invoke"
    return urljoin(endpoint.rstrip("/") + "/", invoke_path.lstrip("/"))


def _peer_payload(peer_name: str, config: dict[str, Any]) -> dict[str, Any]:
    endpoint = _peer_endpoint(config)
    capabilities = config.get("capabilities")
    labels = config.get("labels")
    notes = config.get("notes")
    auth_mode = str(config.get("auth_mode") or ("bearer" if config.get("token") else "none"))
    return {
        "peer": peer_name,
        "label": str(config.get("label") or peer_name),
        "protocol": str(config.get("protocol") or "a2a"),
        "transport": str(config.get("transport") or "http"),
        "endpoint": endpoint,
        "discovery_url": _peer_discovery_url(config),
        "invoke_url": _peer_invoke_url(config),
        "configured": bool(endpoint),
        "auth_mode": auth_mode,
        "capability_count": len(capabilities) if isinstance(capabilities, list) else 0,
        "capabilities": capabilities if isinstance(capabilities, list) else [],
        "labels": labels if isinstance(labels, list) else [],
        "notes": notes if isinstance(notes, list) else [],
        "validation_mode": str(config.get("validation_mode") or "discovery_document"),
        "timeout_seconds": float(config.get("timeout_seconds", 10.0)),
    }


async def list_a2a_peers(settings: Settings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for peer_name, raw in getattr(settings, "llmproxy_a2a_peers", {}).items():
        config = raw if isinstance(raw, dict) else {}
        rows.append(_peer_payload(peer_name, config))
    rows.sort(key=lambda row: str(row.get("label") or row.get("peer") or ""))
    return rows


async def inspect_a2a_peer(settings: Settings, peer_name: str) -> dict[str, Any]:
    config = _peer_config(settings, peer_name)
    payload = _peer_payload(peer_name, config)
    if not payload["configured"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A2A peer is missing an endpoint.")

    headers = {"Accept": "application/json"}
    token = str(config.get("token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=payload["timeout_seconds"], follow_redirects=True) as client:
            response = await client.get(str(payload["discovery_url"]), headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"A2A peer validation failed: {exc}",
        ) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)
    content_type = response.headers.get("content-type", "")
    body: dict[str, Any] | None = None
    parse_error: str | None = None
    try:
        body = response.json()
    except ValueError:
        parse_error = "Discovery endpoint did not return valid JSON."

    discovered_capabilities = []
    if isinstance(body, dict):
        discovered_capabilities = body.get("capabilities") if isinstance(body.get("capabilities"), list) else []
    interaction_traces = [
        build_http_interaction_trace(
            protocol="a2a",
            operation="discovery_document",
            method="GET",
            endpoint=str(payload["discovery_url"]),
            success=response.is_success and body is not None,
            status_code=response.status_code,
            latency_ms=latency_ms,
            source="llmproxy.integrations",
            request_payload={
                "auth_mode": payload["auth_mode"],
                "validation_mode": payload["validation_mode"],
                "headers": {"accept": "application/json"},
            },
            response_payload=body if body is not None else {"parse_error": parse_error},
            peer=payload["peer"],
        )
    ]

    return {
        **payload,
        "validated": response.is_success and body is not None,
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "content_type": content_type,
        "discovery_document": body,
        "discovered_name": body.get("name") if isinstance(body, dict) else None,
        "discovered_description": body.get("description") if isinstance(body, dict) else None,
        "discovered_capability_count": len(discovered_capabilities),
        "discovered_capabilities": discovered_capabilities,
        "parse_error": parse_error,
        "interaction_traces": interaction_traces,
        "interaction_protocols": summarize_interaction_trace_protocols(interaction_traces),
    }


async def invoke_a2a_peer(
    settings: Settings,
    peer_name: str,
    *,
    capability: str,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    config = _peer_config(settings, peer_name)
    payload = _peer_payload(peer_name, config)
    if not payload["configured"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A2A peer is missing an endpoint.")
    if not capability.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A2A capability is required.")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    token = str(config.get("token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request_body = {
        "capability": capability.strip(),
        "input": input_payload,
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=payload["timeout_seconds"], follow_redirects=True) as client:
            response = await client.post(str(payload["invoke_url"]), headers=headers, json=request_body)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"A2A peer invocation failed: {exc}",
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
            protocol="a2a",
            operation="invoke_capability",
            method="POST",
            endpoint=str(payload["invoke_url"]),
            success=response.is_success,
            status_code=response.status_code,
            latency_ms=latency_ms,
            source="llmproxy.integrations",
            request_payload=request_body,
            response_payload=body if body is not None else {"text": text_body, "parse_error": parse_error},
            peer=payload["peer"],
            capability=capability.strip(),
        )
    ]

    return {
        **payload,
        "invoked": True,
        "invoked_capability": capability.strip(),
        "status_code": response.status_code,
        "latency_ms": latency_ms,
        "content_type": content_type,
        "result": body if body is not None else text_body,
        "parse_error": parse_error,
        "interaction_traces": interaction_traces,
        "interaction_protocols": summarize_interaction_trace_protocols(interaction_traces),
    }
