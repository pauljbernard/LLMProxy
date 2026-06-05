"""Administrative operator UI and API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import (
    AuthPrincipal,
    get_runtime_settings,
    get_session,
    require_api_token,
    require_operator_token,
)
from app.config import Settings
from app.db.models import DatasetExport, DatasetImport, DatasetVersion, EvaluationRun, IntegrationEvent, JobQueueRecord, JudgeCritique, ModelPerformanceSample, ModelResponse, RequestLog, RoutingDecisionRecord, TrainingCandidate, TrainingRun
from app.integration.outbox import process_pending_events
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
from app.runtime import run_scheduler_iteration, run_worker_iteration
from app.services.observability import build_operations_summary, log_record, tail_log_records

router = APIRouter(prefix="/admin", tags=["admin"])

STATIC_ROOT = Path(__file__).resolve().parent.parent / "static" / "admin"


class ConfigSetRequest(BaseModel):
    key: str
    value: str
    env_file: str = ".env.local"


class JobRetryRequest(BaseModel):
    reset_attempts: bool = False
    available_now: bool = False

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

@router.get("")
async def admin_console() -> FileResponse:
    return FileResponse(STATIC_ROOT / "index.html")


@router.get("/static/{asset_path:path}")
async def admin_static(asset_path: str) -> FileResponse:
    return FileResponse(STATIC_ROOT / asset_path)


@router.get("/api/config", dependencies=[Depends(require_api_token)])
async def get_config(
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return settings_payload(settings)


@router.get("/api/config/validate", dependencies=[Depends(require_api_token)])
async def validate_config(
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
    }


@router.post("/api/config/set", dependencies=[Depends(require_operator_token)])
async def set_config_value(request: ConfigSetRequest) -> dict[str, Any]:
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
async def get_operations_summary(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return build_operations_summary(session, settings=settings)


@router.get("/api/ops/logs", dependencies=[Depends(require_api_token)])
async def get_operations_logs(
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


@router.get("/api/ops/errors", dependencies=[Depends(require_api_token)])
async def get_operations_errors(
    limit: int = Query(default=100, le=500),
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]]:
    return tail_log_records(settings, limit=limit, errors_only=True)


@router.get("/api/ops/audit", dependencies=[Depends(require_api_token)])
async def get_operations_audit(
    limit: int = Query(default=100, le=500),
    settings: Settings = Depends(get_runtime_settings),
) -> list[dict[str, Any]]:
    return tail_log_records(settings, limit=limit, audit_only=True)


@router.get("/api/ops/live", dependencies=[Depends(require_api_token)])
async def get_operations_live(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> dict[str, Any]:
    return {
        "summary": build_operations_summary(session, settings=settings),
        "logs": tail_log_records(settings, limit=30),
        "errors": tail_log_records(settings, limit=20, errors_only=True),
        "audit": tail_log_records(settings, limit=20, audit_only=True),
    }


@router.get("/api/proxy/requests", dependencies=[Depends(require_api_token)])
async def list_proxy_requests(
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
async def show_proxy_request(
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
async def list_exports(
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
async def list_dataset_imports(
    limit: int = Query(default=20, le=200),
    session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = list(session.execute(select(DatasetImport).order_by(DatasetImport.created_at.desc()).limit(limit)).scalars())
    return [dataset_import_payload(row) for row in rows]


@router.get("/api/datasets/versions", dependencies=[Depends(require_api_token)])
async def list_dataset_versions(
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
async def show_training_run(
    training_run_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(TrainingRun, training_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Training run not found.")
    return training_run_payload(run)


@router.get("/api/evaluation/runs/{evaluation_run_id}", dependencies=[Depends(require_api_token)])
async def show_evaluation_run(
    evaluation_run_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.get(EvaluationRun, evaluation_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found.")
    return evaluation_run_payload(run)


@router.get("/api/jobs", dependencies=[Depends(require_api_token)])
async def list_jobs(
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
async def show_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.get(JobQueueRecord, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job_payload(job)


@router.post("/api/jobs/{job_id}/retry", dependencies=[Depends(require_operator_token)])
async def retry_job(
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
async def cancel_job(
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
async def run_jobs_once(_principal: AuthPrincipal = Depends(require_operator_token)) -> dict[str, Any]:
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
async def list_events(
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
async def show_event(event_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    event = session.get(IntegrationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found.")
    return event_payload(event)


@router.post("/api/events/process", dependencies=[Depends(require_operator_token)])
async def process_events(
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
async def replay_event(
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
async def run_scheduler_once(_principal: AuthPrincipal = Depends(require_operator_token)) -> dict[str, Any]:
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
