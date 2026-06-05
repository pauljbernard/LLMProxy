"""llama.cpp deployment helpers."""

from __future__ import annotations

import json
from pathlib import Path


def deploy_to_llama_cpp(*, model_alias: str, model_package: dict[str, object], models_root: Path) -> dict[str, object]:
    deployment_dir = models_root / model_alias
    deployment_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = deployment_dir / "deployment-llama-cpp.json"
    payload = {
        "model_alias": model_alias,
        "runtime": "llama_cpp",
        "status": "deployed",
        "endpoint_url": "http://localhost:8080",
        "artifact_paths": model_package.get("artifact_paths", []),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "runtime": "llama_cpp",
        "status": "deployed",
        "endpoint_url": payload["endpoint_url"],
        "deployment_manifest_path": str(manifest_path),
    }
