"""LoRA trainer."""

from pathlib import Path

from app.config import Settings
from app.services.command_backend import run_json_command


def _normalize_training_result(
    *,
    artifact_dir: Path,
    training_mode: str,
    raw_result: dict[str, object],
) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metrics = dict(raw_result.get("metrics") or {})
    artifact_path = str(raw_result.get("artifact_path") or artifact_dir)
    checkpoint_path = str(raw_result.get("checkpoint_path") or (artifact_dir / "checkpoint.bin"))
    log_path = str(raw_result.get("log_path") or (artifact_dir / "training.log"))
    metrics_path = str(raw_result.get("metrics_path") or (artifact_dir / "metrics.json"))
    return {
        "status": str(raw_result.get("status", "completed")),
        "metrics": metrics,
        "artifact_path": artifact_path,
        "checkpoint_path": checkpoint_path,
        "log_path": log_path,
        "metrics_path": metrics_path,
        "training_mode": training_mode,
    }


def run_lora(*, artifact_dir: Path, training_config: dict[str, object], settings: Settings) -> dict[str, object]:
    if not settings.llmproxy_lora_trainer_command:
        raise NotImplementedError(
            "Real LoRA training is not configured. Set LLMPROXY_LORA_TRAINER_COMMAND to a command that reads JSON from stdin and emits JSON results."
        )
    raw_result = run_json_command(
        command=settings.llmproxy_lora_trainer_command,
        payload={
            "training_mode": "lora",
            "artifact_dir": str(artifact_dir),
            "training_config": training_config,
        },
        timeout_seconds=settings.llmproxy_training_backend_timeout_seconds,
    )
    return _normalize_training_result(
        artifact_dir=artifact_dir,
        training_mode="lora",
        raw_result=raw_result,
    )
