"""Training orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.virtual_keys import VirtualKeyCreateRequest, create_virtual_key_record
from app.config import Settings
from app.db.models import DatasetVersion, TrainingRun
from app.integration.events import emit_event
from app.integration.jobs import enqueue_training_run_job
from app.proxy.recorder import generate_prefixed_id
from app.schemas.training import TrainingRunRequest, TrainingRunResponse
from app.training.checkpointing import save_json_artifact
from app.training.lora_trainer import run_lora
from app.training.preflight import build_training_preflight
from app.training.qlora_trainer import run_qlora
from app.training.unsloth_trainer import run_unsloth


def list_training_runs(session: Session) -> list[TrainingRun]:
    return list(session.execute(select(TrainingRun).order_by(TrainingRun.started_at.desc())).scalars())


SUPPORTED_TRAINING_MODES = {"lora", "qlora"}
SUPPORTED_TRAINER_BACKENDS = {"custom", "unsloth"}


def create_training_run(
    session: Session,
    *,
    request: TrainingRunRequest,
    settings: Settings,
) -> TrainingRunResponse:
    dataset_version = session.get(DatasetVersion, request.dataset_version_id)
    if dataset_version is None:
        raise ValueError(f"Dataset version '{request.dataset_version_id}' was not found.")
    if request.training_mode not in SUPPORTED_TRAINING_MODES:
        raise ValueError(f"Unsupported training mode '{request.training_mode}'.")
    if request.trainer_backend not in SUPPORTED_TRAINER_BACKENDS:
        raise ValueError(f"Unsupported trainer backend '{request.trainer_backend}'.")
    preflight = build_training_preflight(
        dataset_version=dataset_version,
        request=request,
        settings=settings,
    )
    if not preflight.ready:
        raise ValueError(f"Training preflight failed: {' '.join(preflight.errors)}")

    training_run_id = generate_prefixed_id("train")
    adapter_name = request.adapter_name or f"{dataset_version.domain}-{request.training_mode}-{training_run_id}"
    artifact_dir = Path(settings.llmproxy_checkpoints_path) / training_run_id
    training_config = {
        "dataset_version_id": request.dataset_version_id,
        "training_run_id": training_run_id,
        "dataset_domain": dataset_version.domain,
        "base_model": request.base_model,
        "training_mode": request.training_mode,
        "trainer_backend": request.trainer_backend,
        "epochs": request.epochs,
        "learning_rate": request.learning_rate,
        "adapter_name": adapter_name,
        "train_path": dataset_version.train_path,
        "validation_path": dataset_version.validation_path,
        "test_path": dataset_version.test_path,
        "preflight": preflight.model_dump(),
    }
    training_config["config_path"] = str(artifact_dir / "training-config.json")
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
        trainer_backend=str(training_run.training_config_json.get("trainer_backend", request.trainer_backend)),
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
    trainer_backend = str(training_config.get("trainer_backend", "custom"))
    training_run.status = "running"
    emit_event(
        session,
        event_type="training.started",
        source="llmproxy",
        payload={
            "training_run_id": training_run.id,
            "dataset_version_id": training_run.dataset_version_id,
            "training_mode": training_run.training_mode,
            "trainer_backend": trainer_backend,
        },
    )
    session.flush()
    session.commit()

    trainer_key_record, trainer_raw_token = create_virtual_key_record(
        session,
        VirtualKeyCreateRequest(
            display_name=f"training-run:{training_run.id}",
            owner_id=training_run.id,
            role="automation",
        ),
    )
    training_config = {
        **training_config,
        "proxy_auth": {
            "virtual_key_id": trainer_key_record.id,
            "key_prefix": trainer_key_record.key_prefix,
        },
    }
    training_run.training_config_json = training_config
    session.commit()

    def handle_progress(progress_payload: dict[str, object]) -> None:
        progress_state = {
            **dict(training_run.metrics_json or {}),
            "progress": progress_payload,
        }
        training_run.metrics_json = progress_state
        emit_event(
            session,
            event_type="training.progress",
            source="llmproxy",
            payload={
                "training_run_id": training_run.id,
                "dataset_version_id": training_run.dataset_version_id,
                "training_mode": training_run.training_mode,
                "trainer_backend": trainer_backend,
                "progress": progress_payload,
            },
        )
        session.commit()
    try:
        if trainer_backend == "unsloth":
            trainer_result = run_unsloth(
                artifact_dir=artifact_dir,
                training_config=training_config,
                settings=settings,
                proxy_base_url=settings.llmproxy_internal_api_base_url,
                proxy_api_key=trainer_raw_token,
                progress_callback=handle_progress,
            )
        elif training_run.training_mode == "lora":
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
        training_run.metrics_json = {
            **dict(training_run.metrics_json or {}),
            "error": str(exc),
        }
        training_run.completed_at = datetime.now(timezone.utc)
        trainer_key_record.status = "disabled"
        emit_event(
            session,
            event_type="training.failed",
            source="llmproxy",
            payload={
                "training_run_id": training_run.id,
                "dataset_version_id": training_run.dataset_version_id,
                "training_mode": training_run.training_mode,
                "trainer_backend": trainer_backend,
                "error": str(exc),
            },
        )
        session.commit()
        raise

    training_run.status = str(trainer_result["status"])
    training_run.metrics_json = {
        **dict(training_run.metrics_json or {}),
        **dict(trainer_result["metrics"]),
        "checkpoint_path": trainer_result["checkpoint_path"],
        "log_path": trainer_result["log_path"],
        "metrics_path": trainer_result["metrics_path"],
    }
    training_run.artifact_path = str(trainer_result["artifact_path"])
    training_run.completed_at = datetime.now(timezone.utc)
    trainer_key_record.status = "disabled"
    emit_event(
        session,
        event_type="training.completed",
        source="llmproxy",
        payload={
            "training_run_id": training_run.id,
            "dataset_version_id": training_run.dataset_version_id,
            "training_mode": training_run.training_mode,
            "trainer_backend": trainer_backend,
            "artifact_path": training_run.artifact_path,
        },
    )
    return training_run
