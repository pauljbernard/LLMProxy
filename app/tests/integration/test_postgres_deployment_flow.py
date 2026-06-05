import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app
from app.runtime import run_migrations


def write_package(root: Path, *, model_alias: str) -> None:
    package_dir = root / model_alias
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "model-package.json").write_text(
        json.dumps(
            {
                "package_version": "1.0",
                "model_registry_id": f"model_{model_alias}",
                "model_alias": model_alias,
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "adapter_type": "lora",
                "artifact_format": "adapter-binary",
                "artifact_paths": [str(package_dir / "adapter.bin")],
                "domains": ["coding"],
                "task_types": ["code_review"],
                "quality_summary": {
                    "overall_score": 0.9,
                    "domain_scores": {"coding": 0.9},
                    "quality_delta_vs_frontier": 0.02,
                    "value_per_dollar_gain_vs_frontier": 4.0,
                    "promotion_status": "approved",
                },
                "compatibility": {
                    "model_contract_version": "1.0",
                    "learner_version": "0.1.0",
                    "compatible_proxy_versions": ["0.1.0"],
                    "runtime_targets": ["ollama"],
                },
                "provenance": {"source": "test"},
                "created_at": "2026-06-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_deployment_flow_supports_production_shadow_canary_and_rollback() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("LLMPROXY_TEST_DATABASE_URL is not set")

    with tempfile.TemporaryDirectory() as models_dir:
        write_package(Path(models_dir), model_alias="coding-lora-v1")
        write_package(Path(models_dir), model_alias="coding-lora-v2")

        os.environ["LLMPROXY_DATABASE_URL"] = database_url
        os.environ["LLMPROXY_MODELS_PATH"] = models_dir
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        run_migrations()

        app = create_app()
        client = TestClient(app)

        activate_v1 = client.post(
            "/deployment/models/coding-lora-v1/activate",
            headers={"Authorization": "Bearer change-me"},
            json={"deployment_mode": "production"},
        )
        assert activate_v1.status_code == 200

        response_v1 = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_deploy_v1",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert response_v1.status_code == 200
        assert response_v1.json()["model"] == "coding-lora-v1"

        activate_shadow = client.post(
            "/deployment/models/coding-lora-v2/activate",
            headers={"Authorization": "Bearer change-me"},
            json={"deployment_mode": "shadow"},
        )
        assert activate_shadow.status_code == 200

        shadow_response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_deploy_shadow",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert shadow_response.status_code == 200
        assert shadow_response.json()["model"] == "coding-lora-v1"

        activate_canary = client.post(
            "/deployment/models/coding-lora-v2/activate",
            headers={"Authorization": "Bearer change-me"},
            json={"deployment_mode": "canary", "canary_percent": 1.0},
        )
        assert activate_canary.status_code == 200

        canary_response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_deploy_canary",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert canary_response.status_code == 200
        assert canary_response.json()["model"] == "coding-lora-v2"

        activate_v2_prod = client.post(
            "/deployment/models/coding-lora-v2/activate",
            headers={"Authorization": "Bearer change-me"},
            json={"deployment_mode": "production"},
        )
        assert activate_v2_prod.status_code == 200

        production_v2_response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_deploy_v2",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert production_v2_response.status_code == 200
        assert production_v2_response.json()["model"] == "coding-lora-v2"

        rollback_response = client.post(
            "/deployment/models/coding-lora-v2/rollback",
            headers={"Authorization": "Bearer change-me"},
        )
        assert rollback_response.status_code == 200

        rolled_back_chat = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_deploy_rollback",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert rolled_back_chat.status_code == 200
        assert rolled_back_chat.json()["model"] == "coding-lora-v1"

        local_models = client.get("/models/local", headers={"Authorization": "Bearer change-me"})
        assert local_models.status_code == 200
        assert len(local_models.json()) == 2

        policy_versions = client.get("/deployment/routing-policies", headers={"Authorization": "Bearer change-me"})
        assert policy_versions.status_code == 200
        assert len(policy_versions.json()) >= 5

        session = get_session_factory()()
        try:
            assert session.execute(text("select count(*) from integration.routing_policy_version")).scalar_one() >= 5
            assert session.execute(text("select count(*) from integration.integration_event")).scalar_one() >= 5
            assert session.execute(text("select count(*) from proxy.model_response where response_role = 'shadow_response'")).scalar_one() >= 1
        finally:
            session.close()
