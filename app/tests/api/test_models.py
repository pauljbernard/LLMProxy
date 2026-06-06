import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.dependencies import AuthPrincipal
from app.main import app


def test_list_local_model_packages_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/models/local")
    assert response.status_code == 401


def test_list_local_model_packages_returns_manifests(tmp_path: Path, monkeypatch) -> None:
    from app.api.dependencies import get_runtime_settings, require_api_token
    from app.config import Settings

    package_dir = tmp_path / "train_1"
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_registry_id": "model_train_1",
        "model_alias": "coding-lora-train_1",
        "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "adapter_type": "lora",
        "artifact_paths": ["/tmp/adapter.bin"],
        "domains": ["coding"],
        "quality_summary": {"promotion_status": "approved"},
    }
    (package_dir / "model-package.json").write_text(json.dumps(manifest), encoding="utf-8")

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_models_path=str(tmp_path))
    client = TestClient(app)
    response = client.get("/models/local", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["model_registry_id"] == "model_train_1"
    assert payload[0]["promotion_status"] == "approved"


def test_list_models_filters_results_for_restricted_virtual_key(monkeypatch, tmp_path: Path) -> None:
    from app.api.dependencies import get_runtime_settings, require_api_token
    from app.config import Settings

    package_dir = tmp_path / "train_1"
    package_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "model_registry_id": "model_train_1",
        "model_alias": "coding-lora-train_1",
        "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "adapter_type": "lora",
        "artifact_paths": ["/tmp/adapter.bin"],
        "domains": ["coding"],
        "quality_summary": {"promotion_status": "approved"},
    }
    (package_dir / "model-package.json").write_text(json.dumps(manifest), encoding="utf-8")

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_models_path=str(tmp_path))
    app.dependency_overrides[require_api_token] = lambda: AuthPrincipal(
        token="sk-test",
        role="api",
        key_id="vkey_1",
        models_allowed=("gpt-5.5", "coding-lora-train_1"),
    )
    client = TestClient(app)

    models_response = client.get("/v1/models", headers={"Authorization": "Bearer sk-test"})
    assert models_response.status_code == 200
    model_ids = {item["id"] for item in models_response.json()}
    assert "proxy-auto" in model_ids
    assert "gpt-5.5" in model_ids
    assert "coding-lora-train_1" in model_ids
    assert "claude-3-5-sonnet" not in model_ids

    provider_response = client.get("/models", headers={"Authorization": "Bearer sk-test"})
    assert provider_response.status_code == 200
    provider_ids = {item["model_id"] for item in provider_response.json()}
    assert "gpt-5.5" in provider_ids
    assert "claude-3-5-sonnet" not in provider_ids

    local_response = client.get("/models/local", headers={"Authorization": "Bearer sk-test"})
    app.dependency_overrides.clear()
    assert local_response.status_code == 200
    local_payload = local_response.json()
    assert len(local_payload) == 1
    assert local_payload[0]["model_alias"] == "coding-lora-train_1"
