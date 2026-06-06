"""Outbox processing helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import IntegrationEvent
from app.integration.jobs import (
    enqueue_dataset_import_job,
    enqueue_kpi_report_job,
    has_completed_dataset_import,
)
from app.evaluation.runner import create_evaluation_run
from app.schemas.evaluation import EvaluationRunRequest
from app.schemas.integration import OutboxProcessResponse


def process_pending_events(session: Session, *, settings: Settings) -> OutboxProcessResponse:
    events = list(
        session.execute(
            select(IntegrationEvent).where(IntegrationEvent.processed_at.is_(None)).order_by(IntegrationEvent.occurred_at.asc())
        ).scalars()
    )
    processed_count = 0
    imported_count = 0
    for event in events:
        if event.event_type == "dataset.exported":
            payload = event.payload_json
            if not has_completed_dataset_import(session, dataset_export_id=str(payload["dataset_export_id"])):
                enqueue_dataset_import_job(
                    session,
                    dataset_export_id=str(payload["dataset_export_id"]),
                    manifest_path=str(payload["manifest_path"]),
                    data_path=str(payload["data_path"]),
                )
                imported_count += 1
        elif event.event_type in {"dataset.imported", "training.completed", "evaluation.completed", "model.deployed", "routing.updated"}:
            payload = event.payload_json
            enqueue_kpi_report_job(session)
            if event.event_type == "training.completed":
                create_evaluation_run(
                    session,
                    request=EvaluationRunRequest(training_run_id=str(payload["training_run_id"])),
                    settings=settings,
                )
        event.processed_at = datetime.now(timezone.utc)
        processed_count += 1
    return OutboxProcessResponse(processed_count=processed_count, imported_count=imported_count)
