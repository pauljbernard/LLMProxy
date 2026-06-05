"""Operational logging and monitoring helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    EvaluationRun,
    IntegrationEvent,
    JobQueueRecord,
    ModelPerformanceSample,
    RequestLog,
)

OPS_LOG_FILE = "operations.jsonl"


def _serialize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def log_record(
    settings: Settings,
    *,
    level: str,
    component: str,
    category: str,
    message: str,
    data: dict[str, Any] | None = None,
    audit: bool = False,
) -> dict[str, Any]:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "component": component,
        "category": category,
        "audit": audit,
        "message": message,
        "data": _serialize(data or {}),
    }
    try:
        logs_dir = Path(settings.llmproxy_logs_path)
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / OPS_LOG_FILE
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        return record
    return record


def tail_log_records(
    settings: Settings,
    *,
    limit: int = 100,
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    audit_only: bool = False,
    errors_only: bool = False,
) -> list[dict[str, Any]]:
    log_path = Path(settings.llmproxy_logs_path) / OPS_LOG_FILE
    if not log_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if level and str(record.get("level")) != level.upper():
                continue
            if component and str(record.get("component")) != component:
                continue
            if category and str(record.get("category")) != category:
                continue
            if audit_only and not bool(record.get("audit")):
                continue
            if errors_only and str(record.get("level")) not in {"ERROR", "CRITICAL"}:
                continue
            records.append(record)
    return records[-limit:]


def build_operations_summary(session: Session, *, settings: Settings) -> dict[str, Any]:
    requests = list(session.execute(select(RequestLog).order_by(RequestLog.created_at.desc()).limit(100)).scalars())
    jobs = list(session.execute(select(JobQueueRecord).order_by(JobQueueRecord.created_at.desc()).limit(200)).scalars())
    events = list(session.execute(select(IntegrationEvent).order_by(IntegrationEvent.occurred_at.desc()).limit(200)).scalars())
    samples = list(session.execute(select(ModelPerformanceSample).order_by(ModelPerformanceSample.created_at.desc()).limit(200)).scalars())
    evaluations = list(session.execute(select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(50)).scalars())

    job_counts = {
        "pending": sum(1 for job in jobs if job.status == "pending"),
        "running": sum(1 for job in jobs if job.status == "running"),
        "failed": sum(1 for job in jobs if job.status == "failed"),
        "completed": sum(1 for job in jobs if job.status == "completed"),
        "cancelled": sum(1 for job in jobs if job.status == "cancelled"),
    }
    event_counts = {
        "total": len(events),
        "unprocessed": sum(1 for event in events if event.processed_at is None),
    }
    error_logs = tail_log_records(settings, limit=20, errors_only=True)
    audit_logs = tail_log_records(settings, limit=20, audit_only=True)
    route_counts = {
        "local": sum(1 for sample in samples if str(sample.route_type).startswith("local")),
        "frontier": sum(
            1 for sample in samples if str(sample.route_type).startswith("frontier") or str(sample.route_type) == "fallback"
        ),
        "shadow": sum(1 for sample in samples if str(sample.route_type) == "shadow"),
    }
    latest_request = requests[0].id if requests else None
    latest_evaluation = evaluations[0].id if evaluations else None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logs_path": str(Path(settings.llmproxy_logs_path) / OPS_LOG_FILE),
        "request_count": len(requests),
        "job_counts": job_counts,
        "event_counts": event_counts,
        "route_counts": route_counts,
        "recent_error_count": len(error_logs),
        "recent_audit_count": len(audit_logs),
        "latest_request_id": latest_request,
        "latest_evaluation_run_id": latest_evaluation,
        "provider_configuration": {
            "openai": bool(settings.llmproxy_openai_api_key),
            "anthropic": bool(settings.llmproxy_anthropic_api_key),
            "google": bool(settings.llmproxy_google_api_key),
            "xai": bool(settings.llmproxy_xai_api_key),
            "azure_openai": bool(settings.llmproxy_azure_openai_api_key and settings.llmproxy_azure_openai_endpoint),
            "bedrock": bool(
                settings.llmproxy_bedrock_region
                and settings.llmproxy_bedrock_access_key_id
                and settings.llmproxy_bedrock_secret_access_key
            ),
            "ollama": bool(settings.llmproxy_ollama_base_url),
        },
    }
