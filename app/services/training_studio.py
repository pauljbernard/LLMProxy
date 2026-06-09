"""Unsloth Studio status helpers."""

from __future__ import annotations

import httpx

from app.config import Settings
from app.schemas.training import TrainingStudioStatus


def get_training_studio_status(settings: Settings) -> TrainingStudioStatus:
    enabled = bool(settings.llmproxy_unsloth_studio_enabled)
    external_url = settings.llmproxy_unsloth_studio_url.strip() or None
    internal_url = settings.llmproxy_unsloth_studio_internal_url.strip() or None
    password_configured = bool((settings.llmproxy_unsloth_studio_password or "").strip())
    notes = [
        "Studio is deployed from the upstream unsloth/unsloth image.",
        "Any frontier or OpenAI-compatible traffic launched from Studio should be pointed at LLMProxy.",
        "Shared datasets, models, checkpoints, and reports are mounted from the same llmProxy volumes.",
    ]
    if not enabled:
        return TrainingStudioStatus(
            enabled=False,
            configured=False,
            external_url=external_url,
            internal_url=internal_url,
            password_configured=password_configured,
            reachable=False,
            detail="Unsloth Studio is disabled in configuration.",
            notes=notes,
        )

    if not external_url or not internal_url:
        return TrainingStudioStatus(
            enabled=True,
            configured=False,
            external_url=external_url,
            internal_url=internal_url,
            password_configured=password_configured,
            reachable=False,
            detail="Studio URLs are not fully configured.",
            notes=notes,
        )

    try:
        response = httpx.get(internal_url, follow_redirects=False, timeout=2.0)
        reachable = response.status_code in {200, 302, 303}
        detail = "Studio responded." if reachable else f"Studio returned status {response.status_code}."
        return TrainingStudioStatus(
            enabled=True,
            configured=True,
            external_url=external_url,
            internal_url=internal_url,
            password_configured=password_configured,
            reachable=reachable,
            status_code=response.status_code,
            detail=detail,
            notes=notes,
        )
    except Exception as exc:
        return TrainingStudioStatus(
            enabled=True,
            configured=True,
            external_url=external_url,
            internal_url=internal_url,
            password_configured=password_configured,
            reachable=False,
            detail=str(exc),
            notes=notes,
        )
