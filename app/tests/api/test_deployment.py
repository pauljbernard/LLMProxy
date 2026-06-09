from fastapi.testclient import TestClient

from app.main import app
from app.schemas.integration import DeploymentResponse


def test_deployment_endpoints_require_auth() -> None:
    client = TestClient(app)
    assert client.post("/deployment/models/test/activate", json={"deployment_mode": "production"}).status_code == 401
    assert client.post("/deployment/models/test/rollback").status_code == 401
    assert client.get("/deployment/models/local-inventory").status_code == 401
    assert client.get("/deployment/routing-policies").status_code == 401


def test_deployment_endpoints_require_operator_token() -> None:
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    client = TestClient(app)
    response = client.post(
        "/deployment/models/test/activate",
        headers={"Authorization": "Bearer automation-token"},
        json={"deployment_mode": "production"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 403


def test_activate_model_returns_response(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    class FakeSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "deploy_model",
        lambda session, model_alias, request, settings: DeploymentResponse(
            model_alias=model_alias,
            deployment_mode=request.deployment_mode,
            status="deployed",
            policy_version="rpol_1",
            runtime="ollama",
            endpoint_url="http://localhost:11434",
        ),
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.post(
        "/deployment/models/coding-lora-v1/activate",
        headers={"Authorization": "Bearer change-me"},
        json={"deployment_mode": "production"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "deployed"


def test_rollback_returns_response(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    class FakeSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "rollback_model",
        lambda session, model_alias, settings: DeploymentResponse(
            model_alias=model_alias,
            deployment_mode="rollback",
            status="rolled_back",
            policy_version="rpol_2",
            runtime="ollama",
            endpoint_url="http://localhost:11434",
        ),
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.post(
        "/deployment/models/coding-lora-v1/rollback",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"


def test_upsert_frontier_policy_entry_returns_response(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings, get_session
    from app.config import Settings

    class FakeSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "upsert_frontier_policy_entry",
        lambda session, request: ("rpentry_1", "rpol_9"),
    )

    app.dependency_overrides[get_runtime_settings] = lambda: Settings()
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.post(
        "/deployment/routing-policies/frontier",
        headers={"Authorization": "Bearer change-me"},
        json={
            "provider_key": "openai",
            "model_id": "gpt-5.5",
            "domains": ["general"],
            "tags": ["finance"],
            "regions": ["us-east"],
            "deployment_mode": "production",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["entry_id"] == "rpentry_1"
    assert payload["policy_version"] == "rpol_9"


def test_delete_policy_entry_returns_response(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings, get_session
    from app.config import Settings

    class FakeSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "delete_policy_entry",
        lambda session, entry_id: "rpol_10",
    )

    app.dependency_overrides[get_runtime_settings] = lambda: Settings()
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.delete(
        "/deployment/routing-policies/entries/rpentry_1",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["entry_id"] == "rpentry_1"
    assert payload["policy_version"] == "rpol_10"
    assert payload["action"] == "deleted"


def test_local_deployment_inventory_returns_payload(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings, get_session
    from app.config import Settings

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "list_local_deployment_inventory",
        lambda session, settings: [
            {
                "model_alias": "coding-lora-v1",
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "package_state": "registered",
                "deployment_status": "deployed",
                "deployment_runtime": "ollama",
                "routing_state": "routed_live",
                "lifecycle_stage": "routed_live",
                "endpoint_url": "http://localhost:11434",
                "routed_live": True,
            }
        ],
    )

    app.dependency_overrides[get_runtime_settings] = lambda: Settings()
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get(
        "/deployment/models/local-inventory",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["model_alias"] == "coding-lora-v1"
    assert payload[0]["package_state"] == "registered"
    assert payload[0]["deployment_status"] == "deployed"
    assert payload[0]["routing_state"] == "routed_live"


def test_local_deployment_inventory_supports_paginated_payload(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings, get_session
    from app.config import Settings

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "list_local_deployment_inventory",
        lambda session, settings: [
            {"model_alias": "coding-lora-v1"},
            {"model_alias": "coding-lora-v2"},
            {"model_alias": "coding-lora-v3"},
        ],
    )

    app.dependency_overrides[get_runtime_settings] = lambda: Settings()
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get(
        "/deployment/models/local-inventory?paginated=true&limit=1&offset=1",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert payload["items"][0]["model_alias"] == "coding-lora-v2"


def test_reconcile_ollama_returns_payload(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings, get_session
    from app.config import Settings

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        deployment_api,
        "reconcile_ollama_runtime",
        lambda session, settings: {"runtime": "ollama", "managed_package_count": 1, "packages": []},
    )

    app.dependency_overrides[get_runtime_settings] = lambda: Settings()
    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get(
        "/deployment/runtimes/ollama/reconcile",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["runtime"] == "ollama"


def test_pull_ollama_returns_payload(monkeypatch) -> None:
    from app.api import deployment as deployment_api
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    monkeypatch.setattr(
        deployment_api,
        "pull_ollama_model",
        lambda settings, model_name: {"runtime": "ollama", "model": model_name, "status": "success"},
    )

    app.dependency_overrides[get_runtime_settings] = lambda: Settings()
    client = TestClient(app)
    response = client.post(
        "/deployment/runtimes/ollama/pull",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "Qwen/Qwen2.5-Coder-7B-Instruct"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["model"] == "Qwen/Qwen2.5-Coder-7B-Instruct"
