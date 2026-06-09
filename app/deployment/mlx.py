"""MLX deployment helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import Settings


def deploy_to_mlx(
    *,
    model_alias: str,
    model_package: dict[str, object],
    models_root: Path,
    settings: Settings,
) -> dict[str, object]:
    deployment_dir = models_root / model_alias
    deployment_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = deployment_dir / "deployment-mlx.json"
    payload = {
        "model_alias": model_alias,
        "runtime": "mlx",
        "status": "deployed",
        "endpoint_url": settings.llmproxy_mlx_base_url,
        "artifact_paths": model_package.get("artifact_paths", []),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "runtime": "mlx",
        "status": "deployed",
        "endpoint_url": payload["endpoint_url"],
        "deployment_manifest_path": str(manifest_path),
    }
