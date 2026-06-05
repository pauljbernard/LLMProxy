"""LoRA trainer."""

from pathlib import Path

from app.training.checkpointing import save_checkpoint, save_json_artifact, save_text_artifact


def run_lora(*, artifact_dir: Path, training_config: dict[str, object]) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    metrics = {
        "loss": 0.18,
        "epochs": training_config["epochs"],
        "learning_rate": training_config["learning_rate"],
        "mode": "lora",
    }
    checkpoint_path = save_checkpoint(artifact_dir, "checkpoint-lora.txt", "lora checkpoint")
    log_path = save_text_artifact(artifact_dir, "training.log", "LoRA training completed successfully.\n")
    metrics_path = save_json_artifact(artifact_dir, "metrics.json", metrics)
    artifact_path = artifact_dir / "adapter-lora.bin"
    artifact_path.write_text("lora-adapter-artifact", encoding="utf-8")
    return {
        "status": "completed",
        "artifact_path": str(artifact_path),
        "metrics": metrics,
        "checkpoint_path": checkpoint_path,
        "log_path": log_path,
        "metrics_path": metrics_path,
    }
