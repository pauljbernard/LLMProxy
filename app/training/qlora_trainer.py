"""QLoRA trainer."""

from pathlib import Path


def run_qlora(*, artifact_dir: Path, training_config: dict[str, object]) -> dict[str, object]:
    del artifact_dir, training_config
    raise NotImplementedError(
        "Real QLoRA training is not configured. Wire a supported backend such as mlx_lm.lora or peft/trl before submitting training jobs."
    )
