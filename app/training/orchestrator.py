"""Training orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import DatasetVersion, TrainingRun
from app.integration.events import emit_event
from app.integration.jobs import enqueue_training_run_job
from app.proxy.recorder import generate_prefixed_id
from app.schemas.training import TrainingRunRequest, TrainingRunResponse
from app.training.checkpointing import save_json_artifact
from app.training.lora_trainer import run_lora
from app.training.qlora_trainer import run_qlora


def list_training_runs(session: Session) -> list[TrainingRun]:
    return list(session.execute(select(TrainingRun).order_by(TrainingRun.started_at.desc())).scalars())


def create_training_run(
    session: Session,
    *,
    request: TrainingRunRequest,
    settings: Settings,
) -> TrainingRunResponse:
    dataset_version = session.get(DatasetVersion, request.dataset_version_id)
    if dataset_version is None:
        raise ValueError(f"Dataset version '{request.dataset_version_id}' was not found.")
    if request.training_mode not in {"lora", "qlora"}:
        raise ValueError(f"Unsupported training mode '{request.training_mode}'.")

    training_run_id = generate_prefixed_id("train")
    adapter_name = request.adapter_name or f"{dataset_version.domain}-{request.training_mode}-{training_run_id}"
    artifact_dir = Path(settings.llmproxy_checkpoints_path) / training_run_id
    training_config = {
        "dataset_version_id": request.dataset_version_id,
        "dataset_domain": dataset_version.domain,
        "base_model": request.base_model,
        "training_mode": request.training_mode,
        "epochs": request.epochs,
        "learning_rate": request.learning_rate,
        "adapter_name": adapter_name,
        "train_path": dataset_version.train_path,
        "validation_path": dataset_version.validation_path,
        "test_path": dataset_version.test_path,
    }
    config_path = save_json_artifact(artifact_dir, "training-config.json", training_config)
    training_config["config_path"] = config_path

    training_run = TrainingRun(
        id=training_run_id,
        dataset_version_id=request.dataset_version_id,
        base_model=request.base_model,
        training_mode=request.training_mode,
        status="pending",
        training_config_json=training_config,
        metrics_json={},
        artifact_path=str(artifact_dir),
    )
    session.add(training_run)
    session.flush()
    emit_event(
        session,
        event_type="training.queued",
        source="llmproxy",
        payload={
            "training_run_id": training_run_id,
            "dataset_version_id": request.dataset_version_id,
            "training_mode": request.training_mode,
        },
    )
    enqueue_training_run_job(session, training_run_id=training_run_id)

    return TrainingRunResponse(
        training_run_id=training_run.id,
        dataset_version_id=training_run.dataset_version_id,
        training_mode=training_run.training_mode,
        status=training_run.status,
        artifact_path=training_run.artifact_path,
        metrics=training_run.metrics_json,
    )


def execute_training_run(
    session: Session,
    *,
    training_run_id: str,
    settings: Settings,
) -> TrainingRun:
    training_run = session.get(TrainingRun, training_run_id)
    if training_run is None:
        raise ValueError(f"Training run '{training_run_id}' was not found.")
    if training_run.status == "completed":
        return training_run
    if training_run.status == "running":
        raise RuntimeError(f"Training run '{training_run_id}' is already running.")
    dataset_version = session.get(DatasetVersion, training_run.dataset_version_id)
    if dataset_version is None:
        raise ValueError(f"Dataset version '{training_run.dataset_version_id}' was not found.")

    artifact_dir = Path(settings.llmproxy_checkpoints_path) / training_run.id
    training_config = dict(training_run.training_config_json)
    training_run.status = "running"
    emit_event(
        session,
        event_type="training.started",
        source="llmproxy",
        payload={
            "training_run_id": training_run.id,
            "dataset_version_id": training_run.dataset_version_id,
            "training_mode": training_run.training_mode,
        },
    )
    session.flush()
    try:
        if training_run.training_mode == "lora":
            trainer_result = run_lora(
                artifact_dir=artifact_dir,
                training_config=training_config,
                settings=settings,
            )
        elif training_run.training_mode == "qlora":
            trainer_result = run_qlora(
                artifact_dir=artifact_dir,
                training_config=training_config,
                settings=settings,
            )
        else:
            raise ValueError(f"Unsupported training mode '{training_run.training_mode}'.")
    except Exception as exc:
        training_run.status = "failed"
        training_run.metrics_json = {"error": str(exc)}
        training_run.completed_at = datetime.now(timezone.utc)
        emit_event(
            session,
            event_type="training.failed",
            source="llmproxy",
            payload={
                "training_run_id": training_run.id,
                "dataset_version_id": training_run.dataset_version_id,
                "training_mode": training_run.training_mode,
                "error": str(exc),
            },
        )
        raise

    training_run.status = str(trainer_result["status"])
    training_run.metrics_json = {
        **dict(trainer_result["metrics"]),
        "checkpoint_path": trainer_result["checkpoint_path"],
        "log_path": trainer_result["log_path"],
        "metrics_path": trainer_result["metrics_path"],
    }
    training_run.artifact_path = str(trainer_result["artifact_path"])
    training_run.completed_at = datetime.now(timezone.utc)
    emit_event(
        session,
        event_type="training.completed",
        source="llmproxy",
        payload={
            "training_run_id": training_run.id,
            "dataset_version_id": training_run.dataset_version_id,
            "training_mode": training_run.training_mode,
            "artifact_path": training_run.artifact_path,
        },
    )
    return training_run
