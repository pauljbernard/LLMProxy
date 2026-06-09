import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import Settings
from app.db.models import RoutingPolicyVersion
from app.services.ollama_runtime import pull_ollama_model, reconcile_ollama_runtime


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


def write_package_for_runtime(root: Path, *, model_alias: str, base_model: str, runtime: str) -> None:
    package_dir = root / model_alias
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "model-package.json").write_text(
        json.dumps(
            {
                "model_registry_id": f"model_{model_alias}",
                "model_alias": model_alias,
                "base_model": base_model,
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


def test_reconcile_ollama_runtime_reports_missing_base_models(tmp_path: Path) -> None:
    write_package_for_runtime(
        tmp_path,
        model_alias="coding-lora-v1",
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        runtime="ollama",
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
    settings = Settings(llmproxy_models_path=str(tmp_path), llmproxy_ollama_base_url="http://ollama.local:11434")

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"models": [{"name": "other-model:latest"}]},
        )
    )

    payload = reconcile_ollama_runtime(session, settings=settings, transport=transport)

    assert payload["runtime"] == "ollama"
    assert payload["installed_model_count"] == 1
    assert payload["missing_base_model_count"] == 1
    assert payload["packages"][0]["recommended_action"] == "pull_base_model"


def test_pull_ollama_model_returns_runtime_response() -> None:
    settings = Settings(llmproxy_ollama_base_url="http://ollama.local:11434")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"status": "success"})
    )

    payload = pull_ollama_model(
        settings=settings,
        model_name="Qwen/Qwen2.5-Coder-7B-Instruct",
        transport=transport,
    )

    assert payload["runtime"] == "ollama"
    assert payload["model"] == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert payload["status"] == "success"
