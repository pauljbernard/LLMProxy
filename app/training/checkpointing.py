"""Checkpoint and artifact helpers for training runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_text_artifact(directory: Path, artifact_name: str, payload: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    artifact_path = directory / artifact_name
    artifact_path.write_text(payload, encoding="utf-8")
    return str(artifact_path)


def save_json_artifact(directory: Path, artifact_name: str, payload: dict[str, Any]) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    artifact_path = directory / artifact_name
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(artifact_path)


def save_checkpoint(directory: Path, checkpoint_name: str, payload: str) -> str:
    return save_text_artifact(directory, checkpoint_name, payload)
