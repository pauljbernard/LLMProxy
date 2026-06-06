#!/usr/bin/env python3
"""Example command-backed training adapter for llmProxy.

This is a smoke-test backend that demonstrates the JSON stdin/stdout contract
used by LLMPROXY_LORA_TRAINER_COMMAND and LLMPROXY_QLORA_TRAINER_COMMAND.
It is not a real trainer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    artifact_dir = Path(str(payload["artifact_dir"]))
    artifact_dir.mkdir(parents=True, exist_ok=True)

    training_mode = str(payload.get("training_mode", "lora"))
    training_config = dict(payload.get("training_config") or {})
    checkpoint_path = artifact_dir / f"{training_mode}-adapter.bin"
    log_path = artifact_dir / "training.log"
    metrics_path = artifact_dir / "metrics.json"

    checkpoint_path.write_text("example-adapter-artifact\n", encoding="utf-8")
    log_path.write_text(
        f"example backend executed for {training_mode} with base model {training_config.get('base_model')}\n",
        encoding="utf-8",
    )
    metrics = {
        "loss": 0.1234,
        "epochs": training_config.get("epochs", 0),
        "learning_rate": training_config.get("learning_rate"),
        "backend": "example_lora_backend",
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    json.dump(
        {
            "status": "completed",
            "metrics": metrics,
            "artifact_path": str(artifact_dir),
            "checkpoint_path": str(checkpoint_path),
            "log_path": str(log_path),
            "metrics_path": str(metrics_path),
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
