from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_unsloth_backend_requires_proxy_environment(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "unsloth_backend.py"
    payload = {
        "training_mode": "qlora",
        "artifact_dir": str(tmp_path / "artifacts"),
        "training_config": {
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "epochs": 1,
            "learning_rate": 0.0002,
            "train_path": str(tmp_path / "train.jsonl"),
            "validation_path": str(tmp_path / "valid.jsonl"),
            "config_path": str(tmp_path / "training-config.json"),
        },
    }
    (tmp_path / "train.jsonl").write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")
    (tmp_path / "valid.jsonl").write_text('{"messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"hello"}]}\n', encoding="utf-8")

    env = os.environ.copy()
    env.pop("LLMPROXY_BASE_URL", None)
    env.pop("LLMPROXY_API_KEY", None)

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert completed.returncode == 1
    assert "Missing LLMPROXY_BASE_URL" in completed.stderr
