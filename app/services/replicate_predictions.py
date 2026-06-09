"""Replicate prediction helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import JobQueueRecord
from app.integration.jobs import enqueue_job
from app.services.interaction_traces import build_http_interaction_trace, summarize_interaction_trace_protocols


def enqueue_replicate_prediction_job(
    session: Session,
    *,
    model: str,
    input_payload: dict[str, object],
    wait_for_completion: bool = True,
) -> JobQueueRecord:
    return enqueue_job(
        session,
        job_type="replicate.prediction",
        payload={
            "model": model,
            "input": input_payload,
            "wait_for_completion": wait_for_completion,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        },
    )


async def run_replicate_prediction(
    *,
    settings: Settings,
    model: str,
    input_payload: dict[str, object],
    wait_for_completion: bool = True,
    include_interaction_trace: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    api_token = settings.llmproxy_replicate_api_token
    if not api_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Replicate is not configured. Set LLMPROXY_REPLICATE_API_TOKEN.",
        )

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    if wait_for_completion:
        headers["Prefer"] = "wait"

    started_at = datetime.now(timezone.utc)
    async with httpx.AsyncClient(
        base_url=settings.llmproxy_replicate_base_url.rstrip("/"),
        headers=headers,
        timeout=settings.llmproxy_provider_timeout_seconds,
        transport=transport,
    ) as client:
        response = await client.post(
            "/predictions",
            json={
                "version": model,
                "input": input_payload,
            },
        )
        response.raise_for_status()
        result = response.json()
    if not include_interaction_trace:
        return result
    latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)
    interaction_traces = [
        build_http_interaction_trace(
            protocol="rest",
            operation="prediction_create",
            method="POST",
            endpoint=f"{settings.llmproxy_replicate_base_url.rstrip('/')}/predictions",
            success=True,
            status_code=response.status_code,
            latency_ms=latency_ms,
            source="llmproxy.integrations",
            request_payload={
                "model": model,
                "input": input_payload,
                "wait_for_completion": wait_for_completion,
                "provider": "replicate",
            },
            response_payload=result,
        )
    ]
    return {
        "result": result,
        "interaction_traces": interaction_traces,
        "interaction_protocols": summarize_interaction_trace_protocols(interaction_traces),
    }
