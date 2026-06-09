#!/usr/bin/env python3
"""Real command-backed Unsloth trainer for llmProxy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from training_backend_common import (
    BackendContractError,
    count_jsonl_records,
    emit_error,
    emit_progress,
    emit_streaming_result,
    format_chat_example,
    load_request,
    locate_checkpoint,
    read_jsonl,
    require_proxy_environment,
    select_target_modules,
    write_metrics,
)


def _import_training_stack() -> dict[str, Any]:
    try:
        import torch
        from datasets import Dataset
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastLanguageModel, is_bfloat16_supported
    except ImportError as exc:
        raise BackendContractError(
            "Missing Unsloth training dependencies. Install requirements-training.txt before running the Unsloth backend."
        ) from exc
    return {
        "torch": torch,
        "Dataset": Dataset,
        "FastLanguageModel": FastLanguageModel,
        "SFTConfig": SFTConfig,
        "SFTTrainer": SFTTrainer,
        "is_bfloat16_supported": is_bfloat16_supported,
    }


def _max_seq_length(config: dict[str, Any]) -> int:
    value = config.get("max_seq_length", 4096)
    try:
        return max(512, int(value))
    except (TypeError, ValueError):
        return 4096


def main() -> int:
    try:
        request = load_request()
        config = request.training_config
        artifact_dir = request.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)

        proxy_metadata = require_proxy_environment()
        emit_progress(
            {
                "stage": "boot",
                "trainer_backend": "unsloth",
                "training_mode": request.training_mode,
                "proxy": proxy_metadata,
            }
        )

        train_path = Path(str(config["train_path"]))
        validation_path = Path(str(config["validation_path"]))
        train_count = count_jsonl_records(train_path)
        validation_count = count_jsonl_records(validation_path)
        stack = _import_training_stack()
        torch = stack["torch"]
        cuda_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count()) if cuda_available else 0
        emit_progress(
            {
                "stage": "preflight",
                "train_records": train_count,
                "validation_records": validation_count,
                "cuda_available": cuda_available,
                "device_count": device_count,
            }
        )
        failures: list[str] = []
        if train_count <= 0:
            failures.append(f"Training split is empty: {train_path}")
        if validation_count <= 0:
            failures.append(f"Validation split is empty: {validation_path}")
        if not cuda_available:
            failures.append("Unsloth backend requires a CUDA-enabled GPU in the training-worker container.")
        if failures:
            raise BackendContractError(" ".join(failures))

        train_records = read_jsonl(train_path)
        validation_records = read_jsonl(validation_path)
        emit_progress(
            {
                "stage": "dataset_loaded",
                "train_records": len(train_records),
                "validation_records": len(validation_records),
            }
        )

        Dataset = stack["Dataset"]
        FastLanguageModel = stack["FastLanguageModel"]
        SFTConfig = stack["SFTConfig"]
        SFTTrainer = stack["SFTTrainer"]
        is_bfloat16_supported = stack["is_bfloat16_supported"]

        max_seq_length = _max_seq_length(config)
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(config["base_model"]),
            max_seq_length=max_seq_length,
            load_in_4bit=request.training_mode == "qlora",
        )
        if tokenizer.pad_token is None and tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token

        train_dataset = Dataset.from_list([{"text": format_chat_example(tokenizer, record)} for record in train_records])
        validation_dataset = Dataset.from_list([{"text": format_chat_example(tokenizer, record)} for record in validation_records])

        model = FastLanguageModel.get_peft_model(
            model,
            r=int(config.get("lora_rank", 16 if request.training_mode == "lora" else 8)),
            target_modules=select_target_modules(model),
            lora_alpha=int(config.get("lora_alpha", 16)),
            lora_dropout=float(config.get("lora_dropout", 0.0)),
            bias=str(config.get("lora_bias", "none")),
            use_gradient_checkpointing="unsloth",
            random_state=int(config.get("random_state", 3407)),
            max_seq_length=max_seq_length,
            use_rslora=bool(config.get("use_rslora", False)),
            loftq_config=None,
        )

        log_path = artifact_dir / "training.log"
        metrics_path = artifact_dir / "metrics.json"

        class LogCallback:
            def on_log(self, args, state, control, logs=None, **kwargs):  # type: ignore[no-untyped-def]
                if not logs:
                    return
                interesting = {key: logs[key] for key in ("loss", "eval_loss", "learning_rate", "epoch") if key in logs}
                if not interesting:
                    return
                payload = {"stage": "training", "step": int(getattr(state, "global_step", 0)), **interesting}
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, sort_keys=True) + "\n")
                emit_progress(payload)

        args = SFTConfig(
            output_dir=str(artifact_dir),
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            num_train_epochs=float(config["epochs"]),
            learning_rate=float(config["learning_rate"]),
            per_device_train_batch_size=int(config.get("per_device_train_batch_size", 2)),
            per_device_eval_batch_size=int(config.get("per_device_eval_batch_size", 2)),
            gradient_accumulation_steps=int(config.get("gradient_accumulation_steps", 4)),
            warmup_steps=int(config.get("warmup_steps", 10)),
            logging_steps=int(config.get("logging_steps", 1)),
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=1,
            report_to=[],
            fp16=not bool(is_bfloat16_supported()),
            bf16=bool(is_bfloat16_supported()),
            optim=str(config.get("optim", "adamw_8bit")),
            seed=int(config.get("random_state", 3407)),
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=train_dataset,
            eval_dataset=validation_dataset,
            args=args,
            callbacks=[LogCallback()],
        )

        emit_progress({"stage": "trainer_ready"})
        train_result = trainer.train()
        eval_metrics = trainer.evaluate()
        trainer.model.save_pretrained(str(artifact_dir))
        tokenizer.save_pretrained(str(artifact_dir))

        checkpoint_path = locate_checkpoint(artifact_dir)
        metrics = {
            "trainer_backend": "unsloth",
            "train_loss": float(getattr(train_result, "training_loss", 0.0)),
            "eval_loss": float(eval_metrics.get("eval_loss", 0.0)),
            "epochs": float(config["epochs"]),
            "steps": int(getattr(trainer.state, "global_step", 0)),
            "max_seq_length": max_seq_length,
            "proxy": proxy_metadata,
        }
        write_metrics(metrics_path, metrics)
        emit_progress({"stage": "checkpoint_saved", "checkpoint_path": str(checkpoint_path)})
        return emit_streaming_result(
            artifact_dir=artifact_dir,
            metrics=metrics,
            checkpoint_path=checkpoint_path,
            log_path=log_path,
            metrics_path=metrics_path,
        )
    except BackendContractError as exc:
        return emit_error(str(exc))
    except Exception as exc:  # pragma: no cover - depends on external runtime state
        return emit_error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
