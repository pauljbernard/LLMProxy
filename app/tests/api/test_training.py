from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db.models import TrainingRun
from app.main import app
from app.schemas.training import TrainingPreflightResponse, TrainingRunResponse


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
            trainer_backend=request.trainer_backend,
            status="pending",
            artifact_path="/tmp/train_1",
            metrics={},
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
            "trainer_backend": "unsloth",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["training_run_id"] == "train_1"
    assert payload["status"] == "pending"
    assert payload["trainer_backend"] == "unsloth"


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
                training_config_json={"epochs": 3, "trainer_backend": "unsloth"},
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
    assert payload[0]["trainer_backend"] == "unsloth"


def test_list_training_runs_supports_paginated_payload() -> None:
    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

        def scalars(self):
            return self

        def __iter__(self):
            return iter(self._value)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def close(self) -> None:
            return None

        def execute(self, statement):
            self.calls += 1
            if self.calls == 1:
                return FakeScalarResult(3)
            return FakeScalarResult([
                TrainingRun(
                    id="train_2",
                    dataset_version_id="dsv_2",
                    base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                    training_mode="lora",
                    status="running",
                    training_config_json={"trainer_backend": "unsloth"},
                    metrics_json={"progress": {"stage": "fit", "step": 4}},
                    artifact_path="/tmp/adapter-2.bin",
                    started_at=datetime.now(timezone.utc),
                )
            ])

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get("/training/runs?paginated=true&limit=1&offset=1", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert payload["items"][0]["id"] == "train_2"
    assert payload["items"][0]["trainer_backend"] == "unsloth"


def test_training_preflight_returns_payload(monkeypatch) -> None:
    from app.api import training as training_api

    class FakeSession:
        def close(self) -> None:
            return None

        def get(self, model, object_id):
            if object_id != "dsv_1":
                return None
            return type("DatasetVersion", (), {"id": "dsv_1"})()

    monkeypatch.setattr(
        training_api,
        "build_training_preflight",
        lambda dataset_version, request, settings: TrainingPreflightResponse(
            dataset_version_id=dataset_version.id,
            base_model=request.base_model,
            training_mode=request.training_mode,
            trainer_backend=request.trainer_backend,
            ready=False,
            record_counts={"train": 1, "validation": 0, "test": 0},
            checks=[],
            errors=["Validation split is empty."],
            warnings=[],
        ),
    )

    from app.api.dependencies import get_session

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.post(
        "/training/preflight",
        headers={"Authorization": "Bearer change-me"},
        json={
            "dataset_version_id": "dsv_1",
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "training_mode": "qlora",
            "trainer_backend": "unsloth",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is False
    assert payload["record_counts"]["validation"] == 0
    assert payload["errors"] == ["Validation split is empty."]
