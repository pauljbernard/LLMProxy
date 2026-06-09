from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.db.models import DatasetVersion, TrainingRun
from app.schemas.training import TrainingPreflightResponse, TrainingRunRequest
from app.training.orchestrator import create_training_run, execute_training_run


@dataclass
class _FakeTrainerKeyRecord:
    id: str
    key_prefix: str
    status: str = "active"


class _FakeCreateSession:
    def __init__(self) -> None:
        self.dataset_version = DatasetVersion(
            id="dsv_1",
            domain="coding",
            version_name="v1",
            source_import_id="imp_1",
            train_path="/tmp/train.jsonl",
            validation_path="/tmp/valid.jsonl",
            test_path="/tmp/test.jsonl",
            record_count=10,
        )
        self.added: list[object] = []

    def get(self, model, object_id: str):
        if model is DatasetVersion and object_id == self.dataset_version.id:
            return self.dataset_version
        return None

    def add(self, record: object) -> None:
        self.added.append(record)

    def flush(self) -> None:
        return None


class _FakeExecuteSession:
    def __init__(self, training_run: TrainingRun) -> None:
        self.training_run = training_run
        self.dataset_version = DatasetVersion(
            id="dsv_1",
            domain="coding",
            version_name="v1",
            source_import_id="imp_1",
            train_path="/tmp/train.jsonl",
            validation_path="/tmp/valid.jsonl",
            test_path="/tmp/test.jsonl",
            record_count=10,
        )
        self.commit_count = 0

    def get(self, model, object_id: str):
        if model is TrainingRun and object_id == self.training_run.id:
            return self.training_run
        if model is DatasetVersion and object_id == self.dataset_version.id:
            return self.dataset_version
        return None

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.commit_count += 1


def test_create_training_run_persists_trainer_backend(monkeypatch, tmp_path: Path) -> None:
    from app.training import orchestrator

    session = _FakeCreateSession()
    monkeypatch.setattr(orchestrator, "emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator, "enqueue_training_run_job", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        orchestrator,
        "build_training_preflight",
        lambda **kwargs: TrainingPreflightResponse(
            dataset_version_id="dsv_1",
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            training_mode="qlora",
            trainer_backend="unsloth",
            ready=True,
            record_counts={"train": 1, "validation": 1, "test": 1},
            checks=[],
            errors=[],
            warnings=[],
        ),
    )

    response = create_training_run(
        session,
        request=TrainingRunRequest(
            dataset_version_id="dsv_1",
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            training_mode="qlora",
            trainer_backend="unsloth",
        ),
        settings=Settings(llmproxy_checkpoints_path=str(tmp_path)),
    )

    training_run = next(record for record in session.added if isinstance(record, TrainingRun))
    assert training_run.training_config_json["trainer_backend"] == "unsloth"
    assert response.trainer_backend == "unsloth"


def test_execute_training_run_unsloth_emits_progress_and_disables_key(monkeypatch, tmp_path: Path) -> None:
    from app.training import orchestrator

    training_run = TrainingRun(
        id="train_1",
        dataset_version_id="dsv_1",
        base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
        training_mode="qlora",
        status="pending",
        training_config_json={
            "training_run_id": "train_1",
            "dataset_version_id": "dsv_1",
            "training_mode": "qlora",
            "trainer_backend": "unsloth",
        },
        metrics_json={},
        artifact_path=str(tmp_path / "artifacts"),
    )
    session = _FakeExecuteSession(training_run)
    emitted_events: list[str] = []
    trainer_invocation: dict[str, object] = {}
    fake_record = _FakeTrainerKeyRecord(id="vkey_train_1", key_prefix="sk-training")

    monkeypatch.setattr(orchestrator, "emit_event", lambda *args, **kwargs: emitted_events.append(kwargs["event_type"]))
    monkeypatch.setattr(
        orchestrator,
        "create_virtual_key_record",
        lambda *args, **kwargs: (fake_record, "sk-training-token"),
    )

    def fake_run_unsloth(**kwargs):
        trainer_invocation.update(kwargs)
        kwargs["progress_callback"]({"step": 7, "loss": 0.21})
        return {
            "status": "completed",
            "metrics": {"loss": 0.11},
            "artifact_path": str(tmp_path / "artifacts"),
            "checkpoint_path": str(tmp_path / "artifacts" / "checkpoint.bin"),
            "log_path": str(tmp_path / "artifacts" / "training.log"),
            "metrics_path": str(tmp_path / "artifacts" / "metrics.json"),
        }

    monkeypatch.setattr(orchestrator, "run_unsloth", fake_run_unsloth)

    result = execute_training_run(
        session,
        training_run_id="train_1",
        settings=Settings(
            llmproxy_checkpoints_path=str(tmp_path / "checkpoints"),
            llmproxy_internal_api_base_url="http://api:8000",
        ),
    )

    assert trainer_invocation["proxy_base_url"] == "http://api:8000"
    assert trainer_invocation["proxy_api_key"] == "sk-training-token"
    assert result.metrics_json["progress"] == {"step": 7, "loss": 0.21}
    assert "training.progress" in emitted_events
    assert "training.completed" in emitted_events
    assert fake_record.status == "disabled"
