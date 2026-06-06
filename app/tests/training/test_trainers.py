from pathlib import Path

import pytest

from app.config import Settings
from app.training.lora_trainer import run_lora
from app.training.qlora_trainer import run_qlora


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
