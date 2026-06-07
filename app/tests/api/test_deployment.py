from fastapi.testclient import TestClient

from app.main import app
from app.schemas.integration import DeploymentResponse


def test_deployment_endpoints_require_auth() -> None:
    client = TestClient(app)
    assert client.post("/deployment/models/test/activate", json={"deployment_mode": "production"}).status_code == 401
    assert client.post("/deployment/models/test/rollback").status_code == 401
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
