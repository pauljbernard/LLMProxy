#!/usr/bin/env python3
"""Real command-backed LoRA trainer for llmProxy."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from training_backend_common import (
    BackendContractError,
    emit_error,
    emit_result,
    format_chat_example,
    load_request,
    locate_checkpoint,
    read_jsonl,
    select_target_modules,
    write_metrics,
)


def _import_training_stack() -> dict[str, Any]:
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForCausalLM, AutoTokenizer, TrainerCallback, TrainingArguments
        from trl import SFTTrainer
    except ImportError as exc:
        raise BackendContractError(
            "Missing training dependencies. Install requirements-training.txt before running the LoRA backend."
        ) from exc
    return {
        "torch": torch,
        "Dataset": Dataset,
        "LoraConfig": LoraConfig,
        "TaskType": TaskType,
        "get_peft_model": get_peft_model,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "TrainerCallback": TrainerCallback,
        "TrainingArguments": TrainingArguments,
        "SFTTrainer": SFTTrainer,
    }


def _device_dtype(torch: Any) -> tuple[str, Any]:
    if torch.cuda.is_available():
        return "cuda", torch.bfloat16
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps", torch.float16
    return "cpu", torch.float32


def main() -> int:
    try:
        request = load_request()
        config = request.training_config
        artifact_dir = request.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)

        train_records = read_jsonl(Path(str(config["train_path"])))
        validation_records = read_jsonl(Path(str(config["validation_path"])))

        stack = _import_training_stack()
        torch = stack["torch"]
        Dataset = stack["Dataset"]
        LoraConfig = stack["LoraConfig"]
        TaskType = stack["TaskType"]
        get_peft_model = stack["get_peft_model"]
        AutoModelForCausalLM = stack["AutoModelForCausalLM"]
        AutoTokenizer = stack["AutoTokenizer"]
        TrainerCallback = stack["TrainerCallback"]
        TrainingArguments = stack["TrainingArguments"]
        SFTTrainer = stack["SFTTrainer"]

        device, dtype = _device_dtype(torch)
        tokenizer = AutoTokenizer.from_pretrained(str(config["base_model"]), use_fast=True)
        if tokenizer.pad_token is None and tokenizer.eos_token is not None:
            tokenizer.pad_token = tokenizer.eos_token

        train_dataset = Dataset.from_list([{"text": format_chat_example(tokenizer, record)} for record in train_records])
        validation_dataset = Dataset.from_list([{"text": format_chat_example(tokenizer, record)} for record in validation_records])

        model_kwargs: dict[str, Any] = {"torch_dtype": dtype}
        if device == "cuda":
            model_kwargs["device_map"] = "auto"
        model = AutoModelForCausalLM.from_pretrained(str(config["base_model"]), **model_kwargs)
        if hasattr(model, "config"):
            model.config.use_cache = False

        lora_config = LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
            target_modules=select_target_modules(model),
        )
        model = get_peft_model(model, lora_config)

        log_path = artifact_dir / "training.log"
        metrics_path = artifact_dir / "metrics.json"

        class LogCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):  # type: ignore[override]
                if not logs:
                    return
                interesting = {key: logs[key] for key in ("loss", "eval_loss", "epoch") if key in logs}
                if not interesting:
                    return
                line = json.dumps({"step": state.global_step, **interesting}, sort_keys=True)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                sys.stderr.write(line + "\n")
                sys.stderr.flush()

        training_args = TrainingArguments(
            output_dir=str(artifact_dir),
            num_train_epochs=float(config["epochs"]),
            learning_rate=float(config["learning_rate"]),
            per_device_train_batch_size=int(config.get("per_device_train_batch_size", 1)),
            per_device_eval_batch_size=int(config.get("per_device_eval_batch_size", 1)),
            gradient_accumulation_steps=int(config.get("gradient_accumulation_steps", 4)),
            logging_steps=int(config.get("logging_steps", 10)),
            eval_strategy="epoch",
            save_strategy="epoch",
            save_total_limit=1,
            report_to=[],
            bf16=device == "cuda",
            fp16=device == "mps",
            dataloader_pin_memory=device == "cuda",
            optim="adamw_torch",
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=train_dataset,
            eval_dataset=validation_dataset,
            dataset_text_field="text",
            args=training_args,
            callbacks=[LogCallback()],
        )

        train_result = trainer.train()
        eval_metrics = trainer.evaluate()
        trainer.model.save_pretrained(str(artifact_dir))
        tokenizer.save_pretrained(str(artifact_dir))

        checkpoint_path = locate_checkpoint(artifact_dir)
        metrics = {
            "train_loss": float(getattr(train_result, "training_loss", 0.0)),
            "eval_loss": float(eval_metrics.get("eval_loss", 0.0)),
            "epochs": float(config["epochs"]),
            "steps": int(trainer.state.global_step),
        }
        write_metrics(metrics_path, metrics)
        return emit_result(
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
