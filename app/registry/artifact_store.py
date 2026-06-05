"""Artifact store helpers."""

from __future__ import annotations

import json
from pathlib import Path


def store_artifact(*, directory: Path, artifact_name: str, payload: dict[str, object]) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    artifact_path = directory / artifact_name
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return str(artifact_path)


def list_model_packages(root_directory: Path) -> list[dict[str, object]]:
    if not root_directory.exists():
        return []
    manifests: list[dict[str, object]] = []
    for manifest_path in sorted(root_directory.glob("*/model-package.json")):
        manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
    return manifests


def get_model_package_by_alias(root_directory: Path, model_alias: str) -> dict[str, object] | None:
    for manifest in list_model_packages(root_directory):
        if str(manifest.get("model_alias")) == model_alias:
            return manifest
    return None


def register_model_package(root_directory: Path, registration: dict[str, object]) -> tuple[dict[str, object], str]:
    model_alias = str(registration["model_alias"])
    model_directory = root_directory / model_alias
    model_directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_registry_id": str(registration["model_registry_id"]),
        "model_alias": model_alias,
        "base_model": str(registration["base_model"]),
        "adapter_type": str(registration["adapter_type"]),
        "artifact_paths": [str(registration["adapter_path"])],
        "domains": [str(domain) for domain in registration.get("domains", [])],
        "task_types": [str(task_type) for task_type in registration.get("task_types", [])],
        "runtime": str(registration["runtime"]),
        "endpoint_url": str(registration["endpoint_url"]),
        "quality_summary": registration.get("quality") or {"promotion_status": str(registration["status"])},
        "status": str(registration["status"]),
        "created_at": registration.get("created_at"),
    }
    manifest_path = model_directory / "model-package.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest, str(manifest_path)
