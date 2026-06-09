"""Selected-model periodic monitoring helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import AuthPrincipal
from app.config import Settings
from app.db.models import IntegrationEvent, JobQueueRecord
from app.integration.events import emit_event
from app.integration.jobs import enqueue_job
from app.registry.model_registry import get_provider_registry, resolve_provider
from app.services.observability import log_record

MODEL_MONITOR_EVENT_TYPE = "monitor.llm.checked"
MODEL_MONITOR_EVENT_SOURCE = "model_monitor"


def _monitor_payload_key(monitor: dict[str, Any]) -> str:
    return str(monitor.get("monitor_id") or "").strip()


def _latest_monitor_events(session: Session) -> dict[str, IntegrationEvent]:
    rows = list(
        session.execute(
            select(IntegrationEvent)
            .where(
                IntegrationEvent.event_type == MODEL_MONITOR_EVENT_TYPE,
                IntegrationEvent.source == MODEL_MONITOR_EVENT_SOURCE,
            )
            .order_by(IntegrationEvent.occurred_at.desc())
            .limit(500)
        ).scalars()
    )
    latest: dict[str, IntegrationEvent] = {}
    for row in rows:
        payload = row.payload_json or {}
        monitor_id = str(payload.get("monitor_id") or "").strip()
        if not monitor_id or monitor_id in latest:
            continue
        latest[monitor_id] = row
    return latest


def _queued_monitor_jobs(session: Session) -> set[str]:
    rows = list(
        session.execute(
            select(JobQueueRecord).where(
                JobQueueRecord.job_type == "model.monitor",
                JobQueueRecord.status.in_(("pending", "running")),
            )
        ).scalars()
    )
    return {
        str((row.payload_json or {}).get("monitor_id") or "").strip()
        for row in rows
        if str((row.payload_json or {}).get("monitor_id") or "").strip()
    }


def _monitor_due_at(event: IntegrationEvent | None, *, frequency_minutes: int) -> tuple[datetime | None, bool]:
    if event is None or event.occurred_at is None:
        return None, True
    due_at = event.occurred_at + timedelta(minutes=max(5, int(frequency_minutes)))
    return due_at, due_at <= datetime.now(timezone.utc)


def _monitor_result_summary(event: IntegrationEvent | None) -> dict[str, Any]:
    if event is None:
        return {
            "last_checked_at": None,
            "last_status": "never_checked",
            "last_success": None,
            "last_error": None,
            "last_latency_ms": None,
            "last_request_id": None,
            "last_result": None,
        }
    payload = event.payload_json or {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "last_checked_at": event.occurred_at.isoformat() if event.occurred_at else None,
        "last_status": "ok" if bool(result.get("success")) else "failed",
        "last_success": bool(result.get("success")),
        "last_error": str(result.get("error") or "").strip() or None,
        "last_latency_ms": result.get("latency_ms"),
        "last_request_id": result.get("request_id"),
        "last_result": result,
    }


def list_model_monitors(session: Session, settings: Settings) -> list[dict[str, Any]]:
    latest_events = _latest_monitor_events(session)
    queued_monitors = _queued_monitor_jobs(session)
    rows: list[dict[str, Any]] = []
    for monitor in settings.configured_model_monitors():
        monitor_id = _monitor_payload_key(monitor)
        latest_event = latest_events.get(monitor_id)
        due_at, due_now = _monitor_due_at(
            latest_event,
            frequency_minutes=int(monitor.get("frequency_minutes") or 60),
        )
        rows.append(
            {
                **monitor,
                **_monitor_result_summary(latest_event),
                "queued": monitor_id in queued_monitors,
                "due_at": due_at.isoformat() if due_at else None,
                "due_now": bool(monitor.get("enabled")) and due_now,
            }
        )
    rows.sort(key=lambda item: (not bool(item.get("enabled")), str(item.get("label") or item.get("model_id") or "")))
    return rows


def enqueue_due_model_monitor_jobs(session: Session, *, settings: Settings) -> int:
    latest_events = _latest_monitor_events(session)
    queued_monitors = _queued_monitor_jobs(session)
    enqueued_count = 0
    for monitor in settings.configured_model_monitors():
        monitor_id = _monitor_payload_key(monitor)
        if not bool(monitor.get("enabled")) or not monitor_id or monitor_id in queued_monitors:
            continue
        _, due_now = _monitor_due_at(
            latest_events.get(monitor_id),
            frequency_minutes=int(monitor.get("frequency_minutes") or 60),
        )
        if not due_now:
            continue
        enqueue_job(
            session,
            job_type="model.monitor",
            payload={"monitor_id": monitor_id, "monitor": monitor},
            dedupe_key=("monitor_id", monitor_id),
            max_attempts=1,
        )
        enqueued_count += 1
    return enqueued_count


async def run_model_monitor(
    session: Session,
    *,
    settings: Settings,
    monitor: dict[str, Any],
    operator_token: str,
) -> dict[str, Any]:
    monitor_mode = str(monitor.get("monitor_mode") or "frontdoor_stream")
    provider_key = str(monitor.get("provider_key") or "").strip()
    model_id = str(monitor.get("model_id") or "").strip()
    result: dict[str, Any]
    if monitor_mode == "provider_healthcheck":
        provider_registry = get_provider_registry(settings, session=session)
        provider = resolve_provider(
            settings,
            provider_registry,
            provider_key=provider_key,
            entry={"provider_key": provider_key, "model_id": model_id},
        )
        health = await provider.healthcheck()
        result = {
            "success": bool(health.get("ok")),
            "provider_key": provider_key,
            "model": str(health.get("model") or model_id),
            "requested_model": model_id,
            "status_code": health.get("status_code"),
            "latency_ms": health.get("latency_ms"),
            "error": health.get("error") or health.get("detail") or None,
            "monitor_mode": monitor_mode,
        }
    else:
        from app.api.admin import StreamingValidationRequest, _run_frontdoor_stream_validation

        result = await _run_frontdoor_stream_validation(
            request=StreamingValidationRequest(
                provider_key=provider_key,
                requested_model=model_id,
                prompt=str(monitor.get("prompt") or "Respond with OK."),
                max_chunks=3,
                listener_id=monitor.get("listener_id"),
                execution_mode="interactive",
                validation_scope="default_only",
            ),
            settings=settings,
            session=session,
            principal=AuthPrincipal(token=operator_token, role="operator"),
        )
        result["monitor_mode"] = monitor_mode
    payload = {
        "monitor_id": _monitor_payload_key(monitor),
        "provider_key": provider_key,
        "model_id": model_id,
        "frequency_minutes": int(monitor.get("frequency_minutes") or 60),
        "monitor_mode": monitor_mode,
        "result": result,
    }
    emit_event(
        session,
        event_type=MODEL_MONITOR_EVENT_TYPE,
        source=MODEL_MONITOR_EVENT_SOURCE,
        payload=payload,
    )
    log_record(
        settings,
        level="INFO" if result.get("success") else "ERROR",
        component="observability.model_monitor",
        category="event" if result.get("success") else "error",
        message=f"Model monitor {'succeeded' if result.get('success') else 'failed'} for {provider_key}:{model_id}",
        data=payload,
        audit=True,
    )
    session.commit()
    return payload
