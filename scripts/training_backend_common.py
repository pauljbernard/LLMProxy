#!/usr/bin/env python3
"""Shared helpers for command-backed LoRA/QLoRA training backends."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BackendContractError(RuntimeError):
    """Raised when the training backend contract is violated."""


@dataclass(slots=True)
class TrainingRequest:
    training_mode: str
    artifact_dir: Path
    training_config: dict[str, Any]


def emit_error(message: str) -> int:
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()
    return 1


def load_request() -> TrainingRequest:
    raw_payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(raw_payload, dict):
        raise BackendContractError("Training backend stdin payload must be a JSON object.")

    training_mode = str(raw_payload.get("training_mode") or "").strip()
    artifact_dir = Path(str(raw_payload.get("artifact_dir") or "")).expanduser()
    training_config = raw_payload.get("training_config")

    if not training_mode:
        raise BackendContractError("Missing required field: training_mode")
    if not artifact_dir:
        raise BackendContractError("Missing required field: artifact_dir")
    if not isinstance(training_config, dict):
        raise BackendContractError("Missing required field: training_config")

    required_fields = (
        "base_model",
        "epochs",
        "learning_rate",
        "train_path",
        "validation_path",
        "config_path",
    )
    missing = [field for field in required_fields if not training_config.get(field)]
    if missing:
        raise BackendContractError(f"Missing required training_config fields: {', '.join(missing)}")

    return TrainingRequest(
        training_mode=training_mode,
        artifact_dir=artifact_dir,
        training_config=training_config,
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise BackendContractError(f"Dataset path does not exist: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise BackendContractError(f"Invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(record, dict):
                raise BackendContractError(f"Expected JSON object at {path}:{line_number}")
            rows.append(record)
    if not rows:
        raise BackendContractError(f"Dataset file is empty: {path}")
    return rows


def build_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    messages = list(record.get("messages") or [])
    if not messages:
        raise BackendContractError("Training record is missing messages.")
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "")
        if not role:
            continue
        normalized.append({"role": role, "content": content})
    if not normalized:
        raise BackendContractError("Training record contains no valid messages.")
    if normalized[-1]["role"] != "assistant":
        selected_response = str(record.get("selected_response") or "").strip()
        if not selected_response:
            raise BackendContractError("Training record requires selected_response when the final message is not assistant.")
        normalized.append({"role": "assistant", "content": selected_response})
    return normalized


def format_chat_example(tokenizer: Any, record: dict[str, Any]) -> str:
    messages = build_messages(record)
    chat_template = getattr(tokenizer, "chat_template", None)
    if chat_template:
        try:
            rendered = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False,
            )
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        except Exception:
            pass

    parts: list[str] = []
    for message in messages:
        role = message["role"].strip().lower()
        if role == "system":
            label = "System"
        elif role == "assistant":
            label = "Assistant"
        else:
            label = "Human"
        parts.append(f"### {label}:\n{message['content'].strip()}")
    return "\n\n".join(parts).strip()


def select_target_modules(model: Any) -> list[str]:
    module_names = {name.split(".")[-1] for name, _module in model.named_modules() if name}
    preferred = [name for name in ("q_proj", "v_proj") if name in module_names]
    if preferred:
        return preferred
    fallback_order = (
        "k_proj",
        "o_proj",
        "query_key_value",
        "c_attn",
        "Wqkv",
        "qkv_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    )
    fallbacks = [name for name in fallback_order if name in module_names]
    if fallbacks:
        return fallbacks
    raise BackendContractError(
        "Unable to infer LoRA target modules for the selected base model."
    )


def write_metrics(path: Path, metrics: dict[str, Any]) -> None:
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")


def locate_checkpoint(artifact_dir: Path) -> Path:
    for candidate in (
        artifact_dir / "adapter_model.safetensors",
        artifact_dir / "adapter_model.bin",
    ):
        if candidate.exists():
            return candidate
    raise BackendContractError("Training completed but no adapter checkpoint was written.")


def emit_result(
    *,
    artifact_dir: Path,
    metrics: dict[str, Any],
    checkpoint_path: Path,
    log_path: Path,
    metrics_path: Path,
) -> int:
    json.dump(
        {
            "status": "completed",
            "metrics": metrics,
            "artifact_path": str(artifact_dir),
            "checkpoint_path": str(checkpoint_path),
            "log_path": str(log_path),
            "metrics_path": str(metrics_path),
        },
        sys.stdout,
    )
    sys.stdout.flush()
    return 0

