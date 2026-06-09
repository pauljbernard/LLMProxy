import json
from pathlib import Path
import sys

import pytest

from app.config import Settings
from app.training.lora_trainer import run_lora
from app.training.qlora_trainer import run_qlora
from app.training.unsloth_trainer import run_unsloth


def test_run_lora_uses_configured_backend(monkeypatch, tmp_path: Path) -> None:
    from app.training import lora_trainer

    captured: dict[str, object] = {}

    def fake_run_json_command(**kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "metrics": {"loss": 0.12},
            "artifact_path": str(tmp_path),
        }

    monkeypatch.setattr(lora_trainer, "run_json_command", fake_run_json_command)

    result = run_lora(
        artifact_dir=tmp_path,
        training_config={"base_model": "Qwen/Qwen2.5-Coder-7B-Instruct"},
        settings=Settings(llmproxy_lora_trainer_command="fake-trainer"),
    )

    assert captured["command"] == "fake-trainer"
    assert result["status"] == "completed"
    assert result["metrics"]["loss"] == 0.12


def test_run_qlora_requires_configured_backend(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError):
        run_qlora(
            artifact_dir=tmp_path,
            training_config={"base_model": "Qwen/Qwen2.5-Coder-7B-Instruct"},
            settings=Settings(),
        )


def test_run_unsloth_passes_proxy_credentials_and_progress(monkeypatch, tmp_path: Path) -> None:
    from app.training import unsloth_trainer

    captured: dict[str, object] = {}
    progress_updates: list[dict[str, object]] = []

    def fake_run_json_command_streaming(**kwargs):
        captured.update(kwargs)
        kwargs["progress_callback"]({"step": 2, "loss": 0.31})
        return {
            "status": "completed",
            "metrics": {"loss": 0.12},
            "artifact_path": str(tmp_path),
        }

    monkeypatch.setattr(unsloth_trainer, "run_json_command_streaming", fake_run_json_command_streaming)

    result = run_unsloth(
        artifact_dir=tmp_path,
        training_config={
            "training_run_id": "train_1",
            "dataset_version_id": "dsv_1",
            "training_mode": "qlora",
        },
        settings=Settings(llmproxy_unsloth_trainer_command="fake-unsloth"),
        proxy_base_url="http://api:8000",
        proxy_api_key="sk-training-token",
        progress_callback=progress_updates.append,
    )

    assert captured["command"] == "fake-unsloth"
    assert captured["payload"]["trainer_backend"] == "unsloth"
    assert captured["extra_env"]["LLMPROXY_BASE_URL"] == "http://api:8000"
    assert captured["extra_env"]["LLMPROXY_API_KEY"] == "sk-training-token"
    assert progress_updates == [{"step": 2, "loss": 0.31}]
    assert result["training_mode"] == "qlora"


def test_run_json_command_streaming_reports_progress(tmp_path: Path) -> None:
    from app.services.command_backend import run_json_command_streaming

    script_path = tmp_path / "streaming_backend.py"
    script_path.write_text(
        "\n".join(
            [
                "import json",
                "import sys",
                "payload = json.load(sys.stdin)",
                "print(json.dumps({'type': 'progress', 'payload': {'stage': 'boot', 'training_mode': payload['training_mode']}}), flush=True)",
                "print(json.dumps({'type': 'result', 'payload': {'status': 'completed', 'metrics': {'loss': 0.42}, 'artifact_path': payload['artifact_dir']}}), flush=True)",
            ]
        ),
        encoding="utf-8",
    )
    progress_events: list[dict[str, object]] = []

    result = run_json_command_streaming(
        command=f"{sys.executable} {script_path}",
        payload={"training_mode": "lora", "artifact_dir": str(tmp_path)},
        timeout_seconds=5,
        progress_callback=progress_events.append,
    )

    assert progress_events == [{"stage": "boot", "training_mode": "lora"}]
    assert result == {
        "status": "completed",
        "metrics": {"loss": 0.42},
        "artifact_path": str(tmp_path),
    }
