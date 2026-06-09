from pathlib import Path

from app.config import Settings
from app.schemas.training import TrainingRuntimeDependencyStatus, TrainingWorkerRuntimeStatus
from app.training.preflight import build_training_preflight
from app.schemas.training import TrainingRunRequest


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(__import__("json").dumps(row) for row in rows) + ("\n" if rows else ""), encoding="utf-8")


def test_build_training_preflight_reports_unsloth_dataset_and_config_gaps(tmp_path: Path) -> None:
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    test_path = tmp_path / "test.jsonl"
    _write_jsonl(train_path, [{"messages": [{"role": "user", "content": "hi"}], "selected_response": "hello"}])
    _write_jsonl(validation_path, [])
    _write_jsonl(test_path, [])

    dataset_version = type(
        "DatasetVersion",
        (),
        {
            "id": "dsv_1",
            "train_path": str(train_path),
            "validation_path": str(validation_path),
            "test_path": str(test_path),
        },
    )()

    result = build_training_preflight(
        dataset_version=dataset_version,
        request=TrainingRunRequest(
            dataset_version_id="dsv_1",
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            training_mode="qlora",
            trainer_backend="unsloth",
        ),
        settings=Settings(llmproxy_unsloth_trainer_command="", llmproxy_internal_api_base_url="http://api:8000"),
    )

    assert result.ready is False
    assert result.record_counts == {"train": 1, "validation": 0, "test": 0}
    assert "Unsloth requires a non-empty validation split." in result.errors
    assert "Unsloth backend command is not configured." in result.errors


def test_build_training_preflight_passes_for_ready_custom_run(tmp_path: Path) -> None:
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    test_path = tmp_path / "test.jsonl"
    rows = [{"messages": [{"role": "user", "content": "hi"}], "selected_response": "hello"}]
    _write_jsonl(train_path, rows)
    _write_jsonl(validation_path, rows)
    _write_jsonl(test_path, rows)

    dataset_version = type(
        "DatasetVersion",
        (),
        {
            "id": "dsv_1",
            "train_path": str(train_path),
            "validation_path": str(validation_path),
            "test_path": str(test_path),
        },
    )()

    result = build_training_preflight(
        dataset_version=dataset_version,
        request=TrainingRunRequest(
            dataset_version_id="dsv_1",
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            training_mode="lora",
            trainer_backend="custom",
        ),
        settings=Settings(),
    )

    assert result.ready is True
    assert result.errors == []


def test_build_training_preflight_includes_worker_runtime_status(monkeypatch, tmp_path: Path) -> None:
    from app.training import preflight as preflight_module

    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    test_path = tmp_path / "test.jsonl"
    rows = [{"messages": [{"role": "user", "content": "hi"}], "selected_response": "hello"}]
    _write_jsonl(train_path, rows)
    _write_jsonl(validation_path, rows)
    _write_jsonl(test_path, rows)

    monkeypatch.setattr(
        preflight_module,
        "get_reported_training_runtime_status",
        lambda: TrainingWorkerRuntimeStatus(
            ready=True,
            backend_import_ready=True,
            unsloth_command_configured=True,
            unsloth_command="python scripts/unsloth_backend.py",
            internal_api_base_url="http://api:8000",
            cuda_available=True,
            device_count=1,
            torch_version="2.7.0",
            unsloth_version="2026.6.0",
            dependencies=[
                TrainingRuntimeDependencyStatus(name="torch", available=True, detail="importable"),
                TrainingRuntimeDependencyStatus(name="unsloth", available=True, detail="importable"),
            ],
        ),
    )

    dataset_version = type(
        "DatasetVersion",
        (),
        {
            "id": "dsv_1",
            "train_path": str(train_path),
            "validation_path": str(validation_path),
            "test_path": str(test_path),
        },
    )()

    result = build_training_preflight(
        dataset_version=dataset_version,
        request=TrainingRunRequest(
            dataset_version_id="dsv_1",
            base_model="Qwen/Qwen2.5-Coder-7B-Instruct",
            training_mode="qlora",
            trainer_backend="unsloth",
        ),
        settings=Settings(
            llmproxy_unsloth_trainer_command="python scripts/unsloth_backend.py",
            llmproxy_internal_api_base_url="http://api:8000",
        ),
    )

    assert result.ready is True
    assert result.worker_runtime_status is not None
    assert result.worker_runtime_status.cuda_available is True
    assert any(check.name == "worker_backend_imports" and check.status == "ok" for check in result.checks)
