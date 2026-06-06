"""Persisted job queue helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import DatasetImport, JobQueueRecord
from app.proxy.recorder import generate_prefixed_id
from app.services.observability import log_record


def enqueue_job(
    session: Session,
    *,
    job_type: str,
    payload: dict[str, object],
    dedupe_key: tuple[str, str] | None = None,
    max_attempts: int = 3,
) -> JobQueueRecord:
    if dedupe_key is not None:
        field_name, field_value = dedupe_key
        existing_jobs = list(
            session.execute(
                select(JobQueueRecord).where(
                    JobQueueRecord.job_type == job_type,
                    JobQueueRecord.status.in_(("pending", "running")),
                )
            ).scalars()
        )
        for job in existing_jobs:
            candidate_value = job.job_type if field_name == "job_type" else job.payload_json.get(field_name)
            if str(candidate_value) == field_value:
                return job

    job = JobQueueRecord(
        id=generate_prefixed_id("job"),
        job_type=job_type,
        status="pending",
        payload_json=payload,
        max_attempts=max_attempts,
    )
    session.add(job)
    try:
        log_record(
            get_settings(),
            level="INFO",
            component="integration.jobs",
            category="job",
            message=f"Job enqueued: {job_type}",
            data={"job_id": job.id, "job_type": job_type, "payload": payload},
        )
    except Exception:
        pass
    return job


def enqueue_dataset_import_job(
    session: Session,
    *,
    dataset_export_id: str,
    manifest_path: str,
    data_path: str,
) -> JobQueueRecord:
    return enqueue_job(
        session,
        job_type="dataset.import",
        payload={
            "dataset_export_id": dataset_export_id,
            "manifest_path": manifest_path,
            "data_path": data_path,
        },
        dedupe_key=("dataset_export_id", dataset_export_id),
    )


def enqueue_kpi_report_job(session: Session) -> JobQueueRecord:
    return enqueue_job(
        session,
        job_type="kpi.generate",
        payload={},
        dedupe_key=("job_type", "kpi.generate"),
    )


def enqueue_training_run_job(session: Session, *, training_run_id: str) -> JobQueueRecord:
    return enqueue_job(
        session,
        job_type="training.run",
        payload={"training_run_id": training_run_id},
        dedupe_key=("training_run_id", training_run_id),
    )


def enqueue_retraining_plan_job(
    session: Session,
    *,
    trigger_event_type: str,
    payload: dict[str, object],
) -> JobQueueRecord:
    return enqueue_job(
        session,
        job_type="retraining.plan",
        payload={"trigger_event_type": trigger_event_type, **payload},
    )


def enqueue_performance_sampling_job(
    session: Session,
    *,
    trigger_event_type: str,
    payload: dict[str, object],
) -> JobQueueRecord:
    return enqueue_job(
        session,
        job_type="performance.sample",
        payload={"trigger_event_type": trigger_event_type, **payload},
    )


def claim_next_job(session: Session) -> JobQueueRecord | None:
    return claim_next_job_for_lane(session)


def claim_next_job_for_lane(
    session: Session,
    *,
    include_job_types: set[str] | None = None,
    exclude_job_types: set[str] | None = None,
) -> JobQueueRecord | None:
    now = datetime.now(timezone.utc)
    statement = (
        select(JobQueueRecord)
        .where(
            JobQueueRecord.status == "pending",
            JobQueueRecord.available_at <= now,
        )
        .order_by(JobQueueRecord.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if include_job_types:
        statement = statement.where(JobQueueRecord.job_type.in_(sorted(include_job_types)))
    if exclude_job_types:
        statement = statement.where(JobQueueRecord.job_type.not_in(sorted(exclude_job_types)))
    job = session.execute(statement).scalars().first()
    if job is None:
        return None
    job.status = "running"
    job.claimed_at = now
    job.attempts += 1
    return job


def mark_job_completed(job: JobQueueRecord) -> None:
    job.status = "completed"
    job.completed_at = datetime.now(timezone.utc)
    job.last_error = None
    try:
        log_record(
            get_settings(),
            level="INFO",
            component="integration.jobs",
            category="job",
            message=f"Job completed: {job.job_type}",
            data={"job_id": job.id, "job_type": job.job_type, "attempts": job.attempts},
        )
    except Exception:
        pass


def mark_job_failed(job: JobQueueRecord, *, error: str) -> None:
    job.last_error = error
    if job.attempts >= job.max_attempts:
        job.status = "failed"
    else:
        job.status = "pending"
        job.claimed_at = None
    try:
        log_record(
            get_settings(),
            level="ERROR",
            component="integration.jobs",
            category="error",
            message=f"Job failed: {job.job_type}",
            data={
                "job_id": job.id,
                "job_type": job.job_type,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "status": job.status,
                "error": error,
            },
        )
    except Exception:
        pass


def has_completed_dataset_import(session: Session, *, dataset_export_id: str) -> bool:
    existing = session.execute(
        select(DatasetImport).where(DatasetImport.dataset_export_id == dataset_export_id)
    ).scalars().first()
    return existing is not None
