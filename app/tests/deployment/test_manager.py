import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.db.models import RoutingPolicyVersion
from app.deployment.manager import deploy_model, list_local_deployment_inventory, rollback_model, upsert_frontier_policy_entry
from app.schemas.integration import DeploymentRequest, FrontierPolicyEntryRequest


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def first(self):
        return self._items[0] if self._items else None

    def __iter__(self):
        return iter(self._items)


class FakeSession:
    def __init__(self, existing_policy: RoutingPolicyVersion | None = None) -> None:
        self.existing_policy = existing_policy
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    def execute(self, _statement):
        items = [self.existing_policy] if self.existing_policy is not None else []
        return FakeScalarResult(items)


def write_package(root: Path, *, model_alias: str) -> None:
    write_package_for_runtime(root, model_alias=model_alias, runtime="ollama")


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


def test_deploy_model_persists_policy_and_event(tmp_path: Path) -> None:
    write_package(tmp_path, model_alias="coding-lora-v1")
    session = FakeSession()
    settings = Settings(llmproxy_models_path=str(tmp_path))

    response = deploy_model(
        session,
        model_alias="coding-lora-v1",
        request=DeploymentRequest(deployment_mode="production"),
        settings=settings,
    )

    assert response.status == "deployed"
    assert response.runtime == "ollama"
    assert len(session.added) == 3


def test_deploy_model_supports_vllm_runtime(tmp_path: Path) -> None:
    write_package_for_runtime(tmp_path, model_alias="coding-lora-vllm", runtime="vllm")
    session = FakeSession()
    settings = Settings(llmproxy_models_path=str(tmp_path), llmproxy_vllm_base_url="http://gpu-node-2:8001/v1")

    response = deploy_model(
        session,
        model_alias="coding-lora-vllm",
        request=DeploymentRequest(deployment_mode="production"),
        settings=settings,
    )

    assert response.status == "deployed"
    assert response.runtime == "vllm"
    assert response.endpoint_url == "http://gpu-node-2:8001/v1"


def test_deploy_model_uses_configured_ollama_base_url(tmp_path: Path) -> None:
    write_package(tmp_path, model_alias="coding-lora-v1")
    session = FakeSession()
    settings = Settings(llmproxy_models_path=str(tmp_path), llmproxy_ollama_base_url="http://gpu-node-1:11434")

    response = deploy_model(
        session,
        model_alias="coding-lora-v1",
        request=DeploymentRequest(deployment_mode="production"),
        settings=settings,
    )

    assert response.status == "deployed"
    assert response.runtime == "ollama"
    assert response.endpoint_url == "http://gpu-node-1:11434"


def test_rollback_model_restores_previous_entry(tmp_path: Path) -> None:
    write_package(tmp_path, model_alias="coding-lora-v1")
    write_package(tmp_path, model_alias="coding-lora-v2")
    policy = RoutingPolicyVersion(
        id="rpol_existing",
        policy_version="rpol_existing",
        policy_json={
            "entries": [
                {
                    "model_alias": "coding-lora-v1",
                    "deployment_mode": "previous",
                    "runtime": "ollama",
                    "provider_name": "ollama",
                    "endpoint_url": "http://localhost:11434",
                    "domains": ["coding"],
                },
                {
                    "model_alias": "coding-lora-v2",
                    "deployment_mode": "production",
                    "runtime": "ollama",
                    "provider_name": "ollama",
                    "endpoint_url": "http://localhost:11434",
                    "domains": ["coding"],
                },
            ]
        },
        created_at=datetime.now(timezone.utc),
    )
    session = FakeSession(existing_policy=policy)
    settings = Settings(llmproxy_models_path=str(tmp_path))

    response = rollback_model(session, model_alias="coding-lora-v2", settings=settings)

    assert response.status == "rolled_back"
    assert len(session.added) == 3


def test_local_deployment_inventory_distinguishes_registered_deployed_and_routed(tmp_path: Path) -> None:
    write_package(tmp_path, model_alias="coding-lora-v1")
    deployment_manifest_path = tmp_path / "coding-lora-v1" / "deployment.json"
    deployment_manifest_path.write_text(
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

    payload = list_local_deployment_inventory(session, settings=settings)

    assert payload[0]["package_state"] == "registered"
    assert payload[0]["deployment_status"] == "deployed"
    assert payload[0]["routing_state"] == "routed_live"
    assert payload[0]["lifecycle_stage"] == "routed_live"


def test_upsert_frontier_policy_entry_persists_listener_ids() -> None:
    session = FakeSession()

    entry_id, policy_version = upsert_frontier_policy_entry(
        session,
        request=FrontierPolicyEntryRequest(
            provider_key="openai",
            model_id="gpt-5.5",
            domains=["general"],
            listener_ids=["public-api", "internal-tools"],
            deployment_mode="production",
        ),
    )

    assert entry_id
    assert policy_version
    policy_record = next(item for item in session.added if isinstance(item, RoutingPolicyVersion))
    assert policy_record.policy_json["entries"][0]["listener_ids"] == ["public-api", "internal-tools"]


def test_upsert_frontier_policy_entry_persists_requested_models() -> None:
    session = FakeSession()

    entry_id, policy_version = upsert_frontier_policy_entry(
        session,
        request=FrontierPolicyEntryRequest(
            provider_key="anthropic",
            model_id="claude-sonnet-4-6",
            requested_models=["claude-3-5-sonnet"],
            domains=["general"],
            deployment_mode="production",
        ),
    )

    assert entry_id
    assert policy_version
    policy_record = next(item for item in session.added if isinstance(item, RoutingPolicyVersion))
    assert policy_record.policy_json["entries"][0]["requested_models"] == ["claude-3-5-sonnet"]
