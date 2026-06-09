"""Unsloth trainer adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.config import Settings
from app.services.command_backend import run_json_command_streaming
from app.training.lora_trainer import _normalize_training_result


def run_unsloth(
    *,
    artifact_dir: Path,
    training_config: dict[str, object],
    settings: Settings,
    proxy_base_url: str,
    proxy_api_key: str,
    progress_callback: Callable[[dict[str, object]], None] | None = None,
) -> dict[str, object]:
    if not settings.llmproxy_unsloth_trainer_command:
        raise NotImplementedError(
            "Real Unsloth training is not configured. Set LLMPROXY_UNSLOTH_TRAINER_COMMAND to a command that reads JSON from stdin, emits JSONL progress events, and returns a final JSON result."
        )

    raw_result = run_json_command_streaming(
        command=settings.llmproxy_unsloth_trainer_command,
        payload={
            "trainer_backend": "unsloth",
            "training_mode": str(training_config.get("training_mode", "lora")),
            "artifact_dir": str(artifact_dir),
            "training_config": training_config,
        },
        timeout_seconds=settings.llmproxy_training_backend_timeout_seconds,
        extra_env={
            "LLMPROXY_BASE_URL": proxy_base_url,
            "LLMPROXY_API_KEY": proxy_api_key,
            "LLMPROXY_TRAINER_BACKEND": "unsloth",
            "LLMPROXY_TRAINING_RUN_ID": str(training_config.get("training_run_id", "")),
            "LLMPROXY_DATASET_VERSION_ID": str(training_config.get("dataset_version_id", "")),
        },
        progress_callback=progress_callback,
    )
    return _normalize_training_result(
        artifact_dir=artifact_dir,
        training_mode=str(training_config.get("training_mode", "lora")),
        raw_result=raw_result,
    )
