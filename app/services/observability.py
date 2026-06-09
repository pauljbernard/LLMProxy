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
    RoutingDecisionRecord,
)
from app.services.provider_health import provider_health_snapshot
from app.services.mcp_runtime import mcp_runtime_snapshot

OPS_LOG_FILE = "operations.jsonl"
_REVERSE_READ_CHUNK_SIZE = 8192


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
    offset: int = 0,
    level: str | None = None,
    component: str | None = None,
    category: str | None = None,
    listener_id: str | None = None,
    audit_only: bool = False,
    errors_only: bool = False,
    logs_only: bool = False,
) -> list[dict[str, Any]]:
    log_path = Path(settings.llmproxy_logs_path) / OPS_LOG_FILE
    if not log_path.exists():
        return []

    def record_matches(record: dict[str, Any]) -> bool:
        if level and str(record.get("level")) != level.upper():
            return False
        if component and str(record.get("component")) != component:
            return False
        if category and str(record.get("category")) != category:
            return False
        if listener_id:
            data = record.get("data") or {}
            if not isinstance(data, dict):
                data = {}
            nested_metadata = data.get("metadata") or {}
            if not isinstance(nested_metadata, dict):
                nested_metadata = {}
            normalized_listener = str(data.get("listener_id") or nested_metadata.get("listener_id") or "").strip().lower()
            if normalized_listener != str(listener_id).strip().lower():
                return False
        if audit_only and not bool(record.get("audit")):
            return False
        if errors_only and str(record.get("level")) not in {"ERROR", "CRITICAL"}:
            return False
        if logs_only and (bool(record.get("audit")) or str(record.get("level")) in {"ERROR", "CRITICAL"}):
            return False
        return True

    target = max(0, offset) + max(0, limit)
    if target <= 0:
        return []

    matched: list[dict[str, Any]] = []
    for record in _iter_log_records_reverse(log_path):
        if record_matches(record):
            matched.append(record)
            if len(matched) >= target:
                break
    if not matched:
        return []
    return list(reversed(matched[offset:offset + limit]))


def _iter_log_records_reverse(log_path: Path):
    with log_path.open("rb") as handle:
        handle.seek(0, 2)
        file_position = handle.tell()
        buffer = b""
        while file_position > 0:
            read_size = min(_REVERSE_READ_CHUNK_SIZE, file_position)
            file_position -= read_size
            handle.seek(file_position)
            chunk = handle.read(read_size)
            buffer = chunk + buffer
            lines = buffer.split(b"\n")
            buffer = lines[0]
            for raw_line in reversed(lines[1:]):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
        tail_line = buffer.strip()
        if tail_line:
            try:
                yield json.loads(tail_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return


def build_streaming_telemetry(settings: Settings, *, limit: int = 500) -> dict[str, Any]:
    records = tail_log_records(settings, limit=limit, category="stream")
    stream_started = 0
    stream_completed = 0
    stream_failed = 0
    chunk_counts_by_provider: dict[str, int] = {}
    summaries: list[dict[str, Any]] = []

    for record in records:
        message = str(record.get("message", ""))
        data = record.get("data") or {}
        provider = str(data.get("provider") or data.get("provider_key") or "unknown")
        chunk_count = int(data.get("chunk_count") or 0)

        if "started" in message.lower():
            stream_started += 1
        if "completed" in message.lower():
            stream_completed += 1
            chunk_counts_by_provider[provider] = chunk_counts_by_provider.get(provider, 0) + chunk_count
        if "failed" in message.lower():
            stream_failed += 1

        if str(record.get("component")) in {"proxy.shadow", "proxy.ensemble", "admin.streaming"}:
            summaries.append(
                {
                    "timestamp": record.get("timestamp"),
                    "component": record.get("component"),
                    "message": message,
                    "provider": provider,
                    "model": data.get("model"),
                    "chunk_count": chunk_count or None,
                    "success": data.get("success"),
                    "error": data.get("error"),
                    "request_id": data.get("request_id"),
                }
            )

    return {
        "stream_start_count": stream_started,
        "stream_complete_count": stream_completed,
        "stream_failed_count": stream_failed,
        "chunk_counts_by_provider": chunk_counts_by_provider,
        "recent_stream_summaries": summaries[-20:],
    }


def build_operations_summary(session: Session, *, settings: Settings) -> dict[str, Any]:
    requests = list(session.execute(select(RequestLog).order_by(RequestLog.created_at.desc()).limit(100)).scalars())
    jobs = list(session.execute(select(JobQueueRecord).order_by(JobQueueRecord.created_at.desc()).limit(200)).scalars())
    events = list(session.execute(select(IntegrationEvent).order_by(IntegrationEvent.occurred_at.desc()).limit(200)).scalars())
    samples = list(session.execute(select(ModelPerformanceSample).order_by(ModelPerformanceSample.created_at.desc()).limit(200)).scalars())
    routing_decisions = list(
        session.execute(select(RoutingDecisionRecord).order_by(RoutingDecisionRecord.created_at.desc()).limit(200)).scalars()
    )
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
        "pooled": sum(1 for decision in routing_decisions if decision.selected_pool_id),
        "node_routed": sum(1 for decision in routing_decisions if decision.selected_node_id),
    }
    topology_counts = {
        "pooled_routes": sum(1 for decision in routing_decisions if decision.selected_pool_id),
        "node_routed_routes": sum(1 for decision in routing_decisions if decision.selected_node_id),
        "training_nodes": sum(1 for decision in routing_decisions if str(decision.selected_node_role or "") == "training"),
        "execution_nodes": sum(1 for decision in routing_decisions if str(decision.selected_node_role or "") == "execution"),
        "hybrid_nodes": sum(1 for decision in routing_decisions if str(decision.selected_node_role or "") == "hybrid"),
    }
    latest_request = requests[0].id if requests else None
    latest_evaluation = evaluations[0].id if evaluations else None
    streaming = build_streaming_telemetry(settings)
    provider_health = provider_health_snapshot()
    mcp_runtime = mcp_runtime_snapshot()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "logs_path": str(Path(settings.llmproxy_logs_path) / OPS_LOG_FILE),
        "request_count": len(requests),
        "job_counts": job_counts,
        "event_counts": event_counts,
        "route_counts": route_counts,
        "topology_counts": topology_counts,
        "recent_error_count": len(error_logs),
        "recent_audit_count": len(audit_logs),
        "latest_request_id": latest_request,
        "latest_evaluation_run_id": latest_evaluation,
        "streaming": streaming,
        "provider_health": provider_health,
        "mcp_runtime": mcp_runtime,
        "provider_configuration": settings.provider_configuration,
    }
