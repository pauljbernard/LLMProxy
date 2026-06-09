"""Training-worker runtime capability reporting."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from importlib import import_module
from typing import Any

import redis

from app.config import Settings, get_settings
from app.schemas.training import TrainingRuntimeDependencyStatus, TrainingWorkerRuntimeStatus

_KEY = "llmproxy:training_runtime:status"
_MEMORY_STATUS: dict[str, Any] | None = None
_REDIS: redis.Redis | None = None
_BACKEND_URL: str | None = None


def _resolve_redis() -> redis.Redis | None:
    global _REDIS, _BACKEND_URL
    settings = get_settings()
    redis_url = settings.llmproxy_redis_url
    if _BACKEND_URL == redis_url:
        return _REDIS
    try:
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        client.ping()
        _REDIS = client
    except Exception:
        _REDIS = None
    _BACKEND_URL = redis_url
    return _REDIS


def _with_backend(redis_action, memory_action):
    client = _resolve_redis()
    if client is None:
        return memory_action()
    try:
        return redis_action(client)
    except redis.RedisError:
        return memory_action()


def collect_training_runtime_status(settings: Settings) -> TrainingWorkerRuntimeStatus:
    dependency_rows: list[TrainingRuntimeDependencyStatus] = []
    dependencies_ok = True
    for module_name in ("torch", "transformers", "trl", "datasets", "unsloth"):
        available = importlib.util.find_spec(module_name) is not None
        dependency_rows.append(
            TrainingRuntimeDependencyStatus(
                name=module_name,
                available=available,
                detail="importable" if available else "missing",
            )
        )
        dependencies_ok = dependencies_ok and available

    torch_version: str | None = None
    unsloth_version: str | None = None
    cuda_available: bool | None = None
    device_count: int | None = None
    errors: list[str] = []
    warnings: list[str] = []
    if not settings.llmproxy_unsloth_trainer_command:
        errors.append("LLMPROXY_UNSLOTH_TRAINER_COMMAND is not configured.")
    if not dependencies_ok:
        errors.append("Unsloth training dependencies are not fully importable.")

    if dependencies_ok:
        try:
            torch = import_module("torch")
            torch_version = str(getattr(torch, "__version__", "")) or None
            cuda_available = bool(torch.cuda.is_available())
            device_count = int(torch.cuda.device_count()) if cuda_available else 0
            unsloth = import_module("unsloth")
            unsloth_version = str(getattr(unsloth, "__version__", "")) or None
            if not cuda_available:
                errors.append("No CUDA-enabled GPU is available in the training-worker runtime.")
        except Exception as exc:  # pragma: no cover - depends on runtime imports
            errors.append(f"Training runtime import check failed: {exc}")

    if settings.llmproxy_internal_api_base_url.strip():
        warnings.append("All external trainer-side LLM traffic should target LLMPROXY_INTERNAL_API_BASE_URL.")
    else:
        errors.append("LLMPROXY_INTERNAL_API_BASE_URL is not configured.")

    return TrainingWorkerRuntimeStatus(
        reported_at=datetime.now(timezone.utc),
        ready=not errors,
        backend_import_ready=dependencies_ok,
        unsloth_command_configured=bool(settings.llmproxy_unsloth_trainer_command),
        unsloth_command=settings.llmproxy_unsloth_trainer_command,
        internal_api_base_url=settings.llmproxy_internal_api_base_url,
        cuda_available=cuda_available,
        device_count=device_count,
        torch_version=torch_version,
        unsloth_version=unsloth_version,
        dependencies=dependency_rows,
        errors=errors,
        warnings=warnings,
    )


def report_training_runtime_status(settings: Settings) -> TrainingWorkerRuntimeStatus:
    global _MEMORY_STATUS
    status = collect_training_runtime_status(settings)
    payload = status.model_dump(mode="json")
    _MEMORY_STATUS = payload

    def _write_redis(client: redis.Redis) -> TrainingWorkerRuntimeStatus:
        client.set(_KEY, json.dumps(payload, sort_keys=True), ex=300)
        return status

    def _write_memory() -> TrainingWorkerRuntimeStatus:
        return status

    return _with_backend(_write_redis, _write_memory)


def get_reported_training_runtime_status() -> TrainingWorkerRuntimeStatus | None:
    def _read_redis(client: redis.Redis) -> TrainingWorkerRuntimeStatus | None:
        raw = client.get(_KEY)
        if raw is None:
            return None
        return TrainingWorkerRuntimeStatus.model_validate_json(raw)

    def _read_memory() -> TrainingWorkerRuntimeStatus | None:
        if _MEMORY_STATUS is None:
            return None
        return TrainingWorkerRuntimeStatus.model_validate(_MEMORY_STATUS)

    return _with_backend(_read_redis, _read_memory)
