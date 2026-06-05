import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_list_local_model_packages_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/models/local")
    assert response.status_code == 401


def test_list_local_model_packages_returns_manifests(tmp_path: Path, monkeypatch) -> None:
    from app.api.dependencies import get_runtime_settings
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
