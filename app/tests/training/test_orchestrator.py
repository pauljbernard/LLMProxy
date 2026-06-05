from pathlib import Path

import pytest

from app.config import Settings
from app.db.models import DatasetVersion
from app.training.orchestrator import create_training_run
from app.schemas.training import TrainingRunRequest


class FakeSession:
    def __init__(self, dataset_version: DatasetVersion | None) -> None:
        self._dataset_version = dataset_version
        self.added: list[object] = []
        self.flush_count = 0

    def get(self, model, object_id: str):
        if self._dataset_version is not None and model is DatasetVersion and object_id == self._dataset_version.id:
            return self._dataset_version
        return None

    def add(self, item: object) -> None:
        self.added.append(item)

    def flush(self) -> None:
        self.flush_count += 1


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


def test_create_training_run_persists_artifacts_and_metrics(tmp_path: Path) -> None:
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
    assert response.status == "completed"
    assert Path(response.artifact_path).exists()
    assert Path(response.metrics["checkpoint_path"]).exists()
    assert Path(response.metrics["log_path"]).exists()
    assert Path(response.metrics["metrics_path"]).exists()
    assert len(session.added) == 3
    assert session.flush_count == 1


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
