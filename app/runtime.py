"""Runtime entrypoints for container roles."""

from __future__ import annotations

import argparse
import subprocess
import time
from sqlalchemy import text
import uvicorn

from app.config import get_settings
from app.db.models import EvaluationRun, JobQueueRecord, TrainingRun
from app.db.session import get_engine, get_session_factory
from app.deployment.manager import deploy_model
from app.integration.improvement import build_retraining_plan, record_teacher_comparison_sample
from app.integration.jobs import claim_next_job_for_lane, enqueue_kpi_report_job, mark_job_completed, mark_job_failed
from app.integration.outbox import process_pending_events
from app.integration.performance import generate_kpi_report
from app.datasets.ingestion import import_dataset
from app.evaluation.runner import execute_evaluation_run
from app.schemas.dataset import DatasetImportRequest
from app.schemas.integration import DeploymentRequest
from app.services.observability import log_record
from app.training.orchestrator import execute_training_run


def wait_for_database(timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with get_engine().connect() as connection:
                connection.execute(text("select 1"))
                return
        except Exception as exc:  # pragma: no cover - exercised through runtime validation
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Database did not become ready within {timeout_seconds} seconds") from last_error


def run_migrations() -> None:
    subprocess.run(["python3", "-m", "alembic", "upgrade", "head"], check=True)


def run_api() -> None:
    settings = get_settings()
    wait_for_database(settings.llmproxy_database_wait_timeout_seconds)
    if settings.llmproxy_run_migrations_on_start:
        run_migrations()
    uvicorn.run(
        "app.main:app",
        host=settings.llmproxy_api_host,
        port=settings.llmproxy_api_port,
    )


def run_worker(
    *,
    include_job_types: set[str] | None = None,
    exclude_job_types: set[str] | None = None,
) -> None:
    settings = get_settings()
    wait_for_database(settings.llmproxy_database_wait_timeout_seconds)
    while True:  # pragma: no cover - long-lived runtime role
        try:
            processed = run_worker_iteration(
                include_job_types=include_job_types or settings.worker_include_job_types,
                exclude_job_types=exclude_job_types or settings.worker_exclude_job_types,
            )
        except Exception as exc:
            log_record(
                settings,
                level="ERROR",
                component="runtime.worker",
                category="error",
                message="Worker loop recovered from job failure",
                data={"error": str(exc)},
            )
            time.sleep(1)
            continue
        if not processed:
            time.sleep(5)


def run_scheduler() -> None:
    settings = get_settings()
    wait_for_database(settings.llmproxy_database_wait_timeout_seconds)
    while True:  # pragma: no cover - long-lived runtime role
        try:
            run_scheduler_iteration()
        except Exception as exc:
            log_record(
                settings,
                level="ERROR",
                component="runtime.scheduler",
                category="error",
                message="Scheduler loop recovered from iteration failure",
                data={"error": str(exc)},
            )
        time.sleep(60)


def run_scheduler_iteration() -> None:
    settings = get_settings()
    session = get_session_factory()()
    try:
        result = process_pending_events(session, settings=settings)
        job = enqueue_kpi_report_job(session)
        session.commit()
        log_record(
            settings,
            level="INFO",
            component="runtime.scheduler",
            category="runtime",
            message="Scheduler iteration completed",
            data={"processed_events": result.processed_count, "imported_count": result.imported_count, "kpi_job_id": job.id},
        )
    finally:
        session.close()


def run_worker_iteration(
    *,
    include_job_types: set[str] | None = None,
    exclude_job_types: set[str] | None = None,
) -> bool:
    settings = get_settings()
    session = get_session_factory()()
    job: JobQueueRecord | None = None
    try:
        job = claim_next_job_for_lane(
            session,
            include_job_types=include_job_types or settings.worker_include_job_types,
            exclude_job_types=exclude_job_types or settings.worker_exclude_job_types,
        )
        if job is None:
            session.commit()
            return False

        if job.job_type == "dataset.import":
            import_dataset(
                session,
                request=DatasetImportRequest(
                    dataset_export_id=str(job.payload_json["dataset_export_id"]),
                    manifest_path=str(job.payload_json["manifest_path"]),
                    data_path=str(job.payload_json["data_path"]),
                ),
                settings=settings,
            )
        elif job.job_type == "kpi.generate":
            generate_kpi_report(session, settings=settings)
        elif job.job_type == "performance.sample":
            record_teacher_comparison_sample(
                session,
                trigger_event_type=str(job.payload_json.get("trigger_event_type", "unknown")),
                payload=dict(job.payload_json),
            )
        elif job.job_type == "retraining.plan":
            build_retraining_plan(
                session,
                trigger_event_type=str(job.payload_json.get("trigger_event_type", "unknown")),
                payload=dict(job.payload_json),
            )
        elif job.job_type == "training.run":
            execute_training_run(
                session,
                training_run_id=str(job.payload_json["training_run_id"]),
                settings=settings,
            )
        elif job.job_type == "evaluation.run":
            execute_evaluation_run(
                session,
                evaluation_run_id=str(job.payload_json["evaluation_run_id"]),
                settings=settings,
            )
        elif job.job_type == "deployment.activate":
            deploy_model(
                session,
                model_alias=str(job.payload_json["model_alias"]),
                request=DeploymentRequest(
                    deployment_mode=str(job.payload_json["deployment_mode"]),
                    domains=[str(item) for item in job.payload_json.get("domains", [])] or None,
                    task_types=[str(item) for item in job.payload_json.get("task_types", [])] or None,
                    canary_percent=float(job.payload_json.get("canary_percent", 0.0)),
                ),
                settings=settings,
            )
        else:
            raise RuntimeError(f"Unsupported job type: {job.job_type}")

        mark_job_completed(job)
        session.commit()
        log_record(
            settings,
            level="INFO",
            component="runtime.worker",
            category="runtime",
            message="Worker iteration processed job",
            data={"job_id": job.id, "job_type": job.job_type},
        )
        return True
    except Exception as exc:
        session.rollback()
        retry_session = get_session_factory()()
        try:
            retry_job = retry_session.get(JobQueueRecord, job.id) if job is not None else None
            retry_run_id = str(job.payload_json.get("training_run_id")) if job is not None and job.job_type == "training.run" else None
            retry_run = retry_session.get(TrainingRun, retry_run_id) if retry_run_id else None
            retry_evaluation_run_id = (
                str(job.payload_json.get("evaluation_run_id"))
                if job is not None and job.job_type == "evaluation.run"
                else None
            )
            retry_evaluation_run = retry_session.get(EvaluationRun, retry_evaluation_run_id) if retry_evaluation_run_id else None
            if retry_run is not None:
                retry_run.status = "failed"
                retry_run.metrics_json = {"error": str(exc)}
            if retry_evaluation_run is not None:
                retry_evaluation_run.status = "failed"
                retry_evaluation_run.result_json = {"error": str(exc)}
            if retry_job is not None:
                mark_job_failed(retry_job, error=str(exc))
                retry_session.commit()
        finally:
            retry_session.close()
        log_record(
            settings,
            level="ERROR",
            component="runtime.worker",
            category="error",
            message="Worker iteration failed",
            data={"job_id": job.id if job is not None else None, "error": str(exc)},
        )
        raise
    finally:
        session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="llmProxy runtime entrypoints")
    parser.add_argument("role", choices=["api", "worker", "training-worker", "scheduler", "migrate"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.role == "api":
        run_api()
        return
    if args.role == "worker":
        run_worker()
        return
    if args.role == "training-worker":
        run_worker(include_job_types={"training.run"})
        return
    if args.role == "scheduler":
        run_scheduler()
        return
    run_migrations()


if __name__ == "__main__":
    main()
