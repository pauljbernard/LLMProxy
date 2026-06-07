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
        return response.json()
