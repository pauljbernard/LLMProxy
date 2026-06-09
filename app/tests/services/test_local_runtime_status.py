import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.db.models import RoutingPolicyVersion
from app.services.local_runtime_status import build_local_runtime_status


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None


class FakeSession:
    def __init__(self, existing_policy: RoutingPolicyVersion | None = None) -> None:
        self.existing_policy = existing_policy

    def execute(self, _statement):
        items = [self.existing_policy] if self.existing_policy is not None else []
        return FakeScalarResult(items)


def write_package_for_runtime(root: Path, *, model_alias: str, runtime: str) -> None:
    package_dir = root / model_alias
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "model-package.json").write_text(
        json.dumps(
            {
                "model_registry_id": f"model_{model_alias}",
                "model_alias": model_alias,
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "adapter_type": "lora",
                "artifact_paths": [str(package_dir / "adapter.bin")],
                "domains": ["coding"],
                "task_types": ["code_review"],
                "quality_summary": {"promotion_status": "approved"},
                "compatibility": {"runtime_targets": [runtime]},
            }
        ),
        encoding="utf-8",
    )


def test_build_local_runtime_status_reports_registered_deployed_and_routed_counts(tmp_path: Path) -> None:
    write_package_for_runtime(tmp_path, model_alias="coding-lora-v1", runtime="ollama")
    write_package_for_runtime(tmp_path, model_alias="coding-lora-v2", runtime="ollama")
    (tmp_path / "coding-lora-v1" / "deployment.json").write_text(
        json.dumps(
            {
                "runtime": "ollama",
                "status": "deployed",
                "endpoint_url": "http://gpu-node-1:11434",
            }
        ),
        encoding="utf-8",
    )
    policy = RoutingPolicyVersion(
        id="rpol_existing",
        policy_version="rpol_existing",
        policy_json={
            "entries": [
                {
                    "entry_type": "local",
                    "model_alias": "coding-lora-v1",
                    "deployment_mode": "production",
                    "runtime": "ollama",
                    "provider_name": "ollama",
                    "endpoint_url": "http://gpu-node-1:11434",
                    "domains": ["coding"],
                }
            ]
        },
        created_at=datetime.now(timezone.utc),
    )
    session = FakeSession(existing_policy=policy)
    settings = Settings(llmproxy_models_path=str(tmp_path))

    payload = build_local_runtime_status(session, settings)
    ollama = next(row for row in payload if row["runtime"] == "ollama")

    assert ollama["package_alias_count"] == 2
    assert ollama["deployed_alias_count"] == 1
    assert ollama["active_route_count"] == 1
    assert ollama["deployed_aliases"] == ["coding-lora-v1"]
    assert ollama["active_route_aliases"] == ["coding-lora-v1"]
