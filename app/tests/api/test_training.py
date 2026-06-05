from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.models import TrainingRun
from app.main import app
from app.schemas.training import TrainingRunResponse


def test_training_runs_require_auth() -> None:
    client = TestClient(app)
    response = client.get("/training/runs")
    assert response.status_code == 401


def test_submit_training_run_returns_response(monkeypatch) -> None:
    from app.api import training as training_api

    class FakeSession:
        def commit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        training_api,
        "create_training_run",
        lambda session, request, settings: TrainingRunResponse(
            training_run_id="train_1",
            dataset_version_id=request.dataset_version_id,
            training_mode=request.training_mode,
            status="completed",
            artifact_path="/tmp/adapter.bin",
            metrics={"loss": 0.1},
        ),
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.post(
        "/training/runs",
        headers={"Authorization": "Bearer change-me"},
        json={
            "dataset_version_id": "dsv_1",
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "training_mode": "lora",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["training_run_id"] == "train_1"
    assert payload["status"] == "completed"


def test_list_training_runs_returns_serialized_runs(monkeypatch) -> None:
    from app.api import training as training_api

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        training_api,
        "list_training_runs",
        lambda session: [
            TrainingRun(
                id="train_1",
                dataset_version_id="dsv_1",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                training_mode="qlora",
                status="completed",
                training_config_json={"epochs": 3},
                metrics_json={"loss": 0.15},
                artifact_path="/tmp/adapter.bin",
                started_at=datetime.now(timezone.utc),
            )
        ],
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get("/training/runs", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == "train_1"
    assert payload[0]["training_mode"] == "qlora"

