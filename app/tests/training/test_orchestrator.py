from pathlib import Path

import pytest

from app.config import Settings
from app.db.models import DatasetVersion, TrainingRun
from app.training.orchestrator import create_training_run, execute_training_run
from app.schemas.training import TrainingRunRequest


class FakeSession:
    def __init__(self, dataset_version: DatasetVersion | None, training_run: TrainingRun | None = None) -> None:
        self._dataset_version = dataset_version
        self._training_run = training_run
        self.added: list[object] = []
        self.flush_count = 0
        self.commit_count = 0

    def get(self, model, object_id: str):
        if self._dataset_version is not None and model is DatasetVersion and object_id == self._dataset_version.id:
            return self._dataset_version
        if self._training_run is not None and model is TrainingRun and object_id == self._training_run.id:
            return self._training_run
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def execute(self, _statement):
        class _EmptyResult:
            def scalars(self_inner):
                return []

        return _EmptyResult()

    def flush(self) -> None:
        self.flush_count += 1

    def commit(self) -> None:
        self.commit_count += 1


def build_dataset_version() -> DatasetVersion:
    return DatasetVersion(
        id="dsv_1",
        domain="coding",
        version_name="coding-dsv_1",
        source_import_id="dsimp_1",
        train_path="/tmp/train.jsonl",
        validation_path="/tmp/validation.jsonl",
        test_path="/tmp/test.jsonl",
        record_count=10,
    )


def test_create_training_run_queues_pending_work(tmp_path: Path) -> None:
    session = FakeSession(build_dataset_version())
    settings = Settings(llmproxy_checkpoints_path=str(tmp_path))

    response = create_training_run(
        session,
        request=TrainingRunRequest(
            dataset_version_id="dsv_1",
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            training_mode="lora",
            epochs=4,
            learning_rate=0.0001,
            adapter_name="coding-lora-v1",
        ),
        settings=settings,
    )

    assert response.training_mode == "lora"
    assert response.status == "pending"
    assert Path(response.artifact_path).exists()
    assert response.metrics == {}
    assert len(session.added) == 3
    assert session.flush_count == 1
    artifact_config = Path(response.artifact_path) / "training-config.json"
    assert artifact_config.exists()
    assert "config_path" in artifact_config.read_text(encoding="utf-8")


def test_create_training_run_rejects_missing_dataset_version(tmp_path: Path) -> None:
    session = FakeSession(None)
    settings = Settings(llmproxy_checkpoints_path=str(tmp_path))

    with pytest.raises(ValueError, match="Dataset version 'missing' was not found"):
        create_training_run(
            session,
            request=TrainingRunRequest(
                dataset_version_id="missing",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                training_mode="lora",
            ),
            settings=settings,
        )


def test_create_training_run_rejects_unsupported_mode(tmp_path: Path) -> None:
    session = FakeSession(build_dataset_version())
    settings = Settings(llmproxy_checkpoints_path=str(tmp_path))

    with pytest.raises(ValueError, match="Unsupported training mode 'full_finetune'"):
        create_training_run(
            session,
            request=TrainingRunRequest(
                dataset_version_id="dsv_1",
                base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
                training_mode="full_finetune",
            ),
            settings=settings,
        )


def test_execute_training_run_returns_completed_run_without_rerunning(tmp_path: Path) -> None:
    dataset_version = build_dataset_version()
    training_run = TrainingRun(
        id="train_1",
        dataset_version_id=dataset_version.id,
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        training_mode="lora",
        status="completed",
        training_config_json={},
        metrics_json={"loss": 0.1},
        artifact_path=str(tmp_path / "train_1"),
    )
    session = FakeSession(dataset_version, training_run=training_run)

    result = execute_training_run(session, training_run_id="train_1", settings=Settings(llmproxy_checkpoints_path=str(tmp_path)))

    assert result is training_run


def test_execute_training_run_rejects_duplicate_running_run(tmp_path: Path) -> None:
    dataset_version = build_dataset_version()
    training_run = TrainingRun(
        id="train_1",
        dataset_version_id=dataset_version.id,
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        training_mode="lora",
        status="running",
        training_config_json={},
        metrics_json={},
        artifact_path=str(tmp_path / "train_1"),
    )
    session = FakeSession(dataset_version, training_run=training_run)

    with pytest.raises(RuntimeError, match="already running"):
        execute_training_run(session, training_run_id="train_1", settings=Settings(llmproxy_checkpoints_path=str(tmp_path)))


def test_execute_training_run_commits_running_state_before_backend_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_version = build_dataset_version()
    training_run = TrainingRun(
        id="train_1",
        dataset_version_id=dataset_version.id,
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        training_mode="lora",
        status="pending",
        training_config_json={"epochs": 1, "learning_rate": 0.0002},
        metrics_json={},
        artifact_path=str(tmp_path / "train_1"),
    )
    session = FakeSession(dataset_version, training_run=training_run)

    def fake_run_lora(*, artifact_dir, training_config, settings):
        assert session.commit_count == 1
        assert training_run.status == "running"
        return {
            "status": "completed",
            "metrics": {"train_loss": 0.1},
            "artifact_path": str(artifact_dir),
            "checkpoint_path": str(artifact_dir / "adapter_model.safetensors"),
            "log_path": str(artifact_dir / "training.log"),
            "metrics_path": str(artifact_dir / "metrics.json"),
        }

    monkeypatch.setattr("app.training.orchestrator.run_lora", fake_run_lora)
    result = execute_training_run(session, training_run_id="train_1", settings=Settings(llmproxy_checkpoints_path=str(tmp_path)))

    assert result.status == "completed"
    assert session.commit_count == 1


def test_execute_training_run_persists_failed_status_before_reraising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dataset_version = build_dataset_version()
    training_run = TrainingRun(
        id="train_1",
        dataset_version_id=dataset_version.id,
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        training_mode="lora",
        status="pending",
        training_config_json={"epochs": 1, "learning_rate": 0.0002},
        metrics_json={},
        artifact_path=str(tmp_path / "train_1"),
    )
    session = FakeSession(dataset_version, training_run=training_run)

    def fake_run_lora(*, artifact_dir, training_config, settings):
        raise RuntimeError("trainer boom")

    monkeypatch.setattr("app.training.orchestrator.run_lora", fake_run_lora)
    with pytest.raises(RuntimeError, match="trainer boom"):
        execute_training_run(session, training_run_id="train_1", settings=Settings(llmproxy_checkpoints_path=str(tmp_path)))

    assert training_run.status == "failed"
    assert training_run.metrics_json == {"error": "trainer boom"}
    assert session.commit_count == 2
