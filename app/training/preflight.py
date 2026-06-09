"""Training preflight validation."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings
from app.db.models import DatasetVersion
from app.schemas.training import TrainingPreflightCheck, TrainingPreflightResponse, TrainingRunRequest
from app.services.training_runtime import get_reported_training_runtime_status


def _count_jsonl_records(path: str) -> int:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise ValueError(f"Dataset path does not exist: {dataset_path}")
    record_count = 0
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {dataset_path}:{line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object at {dataset_path}:{line_number}")
            record_count += 1
    return record_count


def build_training_preflight(
    *,
    dataset_version: DatasetVersion,
    request: TrainingRunRequest,
    settings: Settings,
) -> TrainingPreflightResponse:
    runtime_status = get_reported_training_runtime_status()
    record_counts = {
        "train": _count_jsonl_records(dataset_version.train_path),
        "validation": _count_jsonl_records(dataset_version.validation_path),
        "test": _count_jsonl_records(dataset_version.test_path),
    }

    checks: list[TrainingPreflightCheck] = []
    errors: list[str] = []
    warnings: list[str] = []

    checks.append(
        TrainingPreflightCheck(
            name="train_split",
            status="ok" if record_counts["train"] > 0 else "error",
            detail=f"{record_counts['train']} training record(s) found.",
        )
    )
    if record_counts["train"] <= 0:
        errors.append("Training split is empty.")

    validation_required = request.trainer_backend == "unsloth"
    validation_status = "ok" if record_counts["validation"] > 0 else ("error" if validation_required else "warn")
    checks.append(
        TrainingPreflightCheck(
            name="validation_split",
            status=validation_status,
            detail=f"{record_counts['validation']} validation record(s) found.",
        )
    )
    if validation_required and record_counts["validation"] <= 0:
        errors.append("Unsloth requires a non-empty validation split.")
    elif record_counts["validation"] <= 0:
        warnings.append("Validation split is empty.")

    checks.append(
        TrainingPreflightCheck(
            name="test_split",
            status="ok" if record_counts["test"] > 0 else "warn",
            detail=f"{record_counts['test']} test record(s) found.",
        )
    )
    if record_counts["test"] <= 0:
        warnings.append("Test split is empty.")

    if request.trainer_backend == "unsloth":
        unsloth_command = settings.llmproxy_unsloth_trainer_command or ""
        checks.append(
            TrainingPreflightCheck(
                name="unsloth_command",
                status="ok" if unsloth_command.strip() else "error",
                detail=unsloth_command.strip() or "LLMPROXY_UNSLOTH_TRAINER_COMMAND is not configured.",
            )
        )
        if not unsloth_command.strip():
            errors.append("Unsloth backend command is not configured.")

        proxy_base_url = settings.llmproxy_internal_api_base_url.strip()
        checks.append(
            TrainingPreflightCheck(
                name="proxy_base_url",
                status="ok" if proxy_base_url else "error",
                detail=proxy_base_url or "LLMPROXY_INTERNAL_API_BASE_URL is not configured.",
            )
        )
        if not proxy_base_url:
            errors.append("Internal proxy base URL is not configured for trainer-routed LLM traffic.")

        if runtime_status is None:
            checks.append(
                TrainingPreflightCheck(
                    name="worker_runtime_status",
                    status="warn",
                    detail="No recent training-worker runtime report is available yet.",
                )
            )
            warnings.append("Training-worker runtime status is unavailable, so GPU and dependency readiness could not be verified.")
        else:
            checks.append(
                TrainingPreflightCheck(
                    name="worker_runtime_status",
                    status="ok" if runtime_status.reported_at else "warn",
                    detail=f"Latest report at {runtime_status.reported_at.isoformat() if runtime_status.reported_at else 'unknown time'}.",
                )
            )
            checks.append(
                TrainingPreflightCheck(
                    name="worker_backend_imports",
                    status="ok" if runtime_status.backend_import_ready else "error",
                    detail="All Unsloth backend imports are available." if runtime_status.backend_import_ready else "; ".join(runtime_status.errors) or "Unsloth backend imports are not ready.",
                )
            )
            checks.append(
                TrainingPreflightCheck(
                    name="worker_gpu",
                    status="ok" if runtime_status.cuda_available else "error",
                    detail=(
                        f"CUDA available with {runtime_status.device_count or 0} device(s)."
                        if runtime_status.cuda_available
                        else "No CUDA-enabled GPU reported by the training-worker runtime."
                    ),
                )
            )
            if not runtime_status.backend_import_ready:
                errors.append("Training-worker runtime is missing Unsloth dependencies.")
            if runtime_status.cuda_available is False:
                errors.append("Training-worker runtime does not report a CUDA-enabled GPU.")
            warnings.extend(runtime_status.warnings)

    return TrainingPreflightResponse(
        dataset_version_id=dataset_version.id,
        base_model=request.base_model,
        training_mode=request.training_mode,
        trainer_backend=request.trainer_backend,
        ready=not errors,
        record_counts=record_counts,
        checks=checks,
        errors=errors,
        warnings=warnings,
        worker_runtime_status=runtime_status,
    )
