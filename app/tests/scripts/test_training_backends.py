import json
import subprocess
from pathlib import Path


REPO_ROOT = Path("/Volumes/data/development/llmProxy")


def _run_backend(script_name: str, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(REPO_ROOT / "scripts" / script_name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_lora_backend_rejects_missing_required_fields(tmp_path: Path) -> None:
    result = _run_backend(
        "lora_backend.py",
        {
            "training_mode": "lora",
            "artifact_dir": str(tmp_path / "artifacts"),
            "training_config": {"base_model": "missing-fields-only"},
        },
    )

    assert result.returncode != 0
    assert "Missing required training_config fields" in result.stderr
    assert result.stdout == ""


def test_lora_backend_rejects_empty_train_dataset(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    train_path = tmp_path / "train.jsonl"
    validation_path = tmp_path / "validation.jsonl"
    config_path = tmp_path / "training-config.json"

    train_path.write_text("", encoding="utf-8")
    validation_path.write_text('{"messages":[{"role":"user","content":"hi"}],"selected_response":"hello"}\n', encoding="utf-8")
    config_path.write_text("{}", encoding="utf-8")

    result = _run_backend(
        "lora_backend.py",
        {
            "training_mode": "lora",
            "artifact_dir": str(artifact_dir),
            "training_config": {
                "base_model": "test-base-model",
                "epochs": 1,
                "learning_rate": 0.0002,
                "train_path": str(train_path),
                "validation_path": str(validation_path),
                "test_path": str(tmp_path / "test.jsonl"),
                "config_path": str(config_path),
            },
        },
    )

    assert result.returncode != 0
    assert "Dataset file is empty" in result.stderr
    assert result.stdout == ""


def test_qlora_backend_rejects_missing_required_fields(tmp_path: Path) -> None:
    result = _run_backend(
        "qlora_backend.py",
        {
            "training_mode": "qlora",
            "artifact_dir": str(tmp_path / "artifacts"),
            "training_config": {"base_model": "missing-fields-only"},
        },
    )

    assert result.returncode != 0
    assert "Missing required training_config fields" in result.stderr
    assert result.stdout == ""
