"""QLoRA trainer."""

from pathlib import Path

from app.config import Settings
from app.services.command_backend import run_json_command
from app.training.lora_trainer import _normalize_training_result


def run_qlora(*, artifact_dir: Path, training_config: dict[str, object], settings: Settings) -> dict[str, object]:
    if not settings.llmproxy_qlora_trainer_command:
        raise NotImplementedError(
            "Real QLoRA training is not configured. Set LLMPROXY_QLORA_TRAINER_COMMAND to a command that reads JSON from stdin and emits JSON results."
        )
    raw_result = run_json_command(
        command=settings.llmproxy_qlora_trainer_command,
        payload={
            "training_mode": "qlora",
            "artifact_dir": str(artifact_dir),
            "training_config": training_config,
        },
        timeout_seconds=settings.llmproxy_training_backend_timeout_seconds,
    )
    return _normalize_training_result(
        artifact_dir=artifact_dir,
        training_mode="qlora",
        raw_result=raw_result,
    )
