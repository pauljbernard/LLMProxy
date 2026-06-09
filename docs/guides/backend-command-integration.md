# Backend Command Integration

`llmProxy` now supports command-backed training and evaluation backends.

This lets you keep the orchestration, job queue, lifecycle events, model
packaging, and promotion gate inside `llmProxy` while delegating the actual
training or benchmark execution to an external script or executable.

## Purpose

Use this when you want to:

- plug in a real LoRA or QLoRA trainer
- plug in a real benchmark evaluator
- smoke-test the full learner pipeline with a contract adapter before wiring a
  full ML stack

## Environment variables

| Variable | Purpose |
|---|---|
| `LLMPROXY_LORA_TRAINER_COMMAND` | command used for LoRA training runs |
| `LLMPROXY_QLORA_TRAINER_COMMAND` | command used for QLoRA training runs |
| `LLMPROXY_EVALUATION_COMMAND` | command used for benchmark evaluation |
| `LLMPROXY_TRAINING_BACKEND_TIMEOUT_SECONDS` | timeout for training commands |
| `LLMPROXY_EVALUATION_TIMEOUT_SECONDS` | timeout for evaluation commands |

If a command is not configured:

- training still queues correctly, but the worker raises `NotImplementedError`
- evaluation still rejects execution with `NotImplementedError`

That is intentional. The system now fails honestly instead of fabricating
results.

## Command contract

The command is executed as a child process.

- `stdin`: one JSON object
- `stdout`: one JSON object
- non-zero exit code: treated as failure
- invalid JSON output: treated as failure

## Training backend input

The training command receives JSON like:

```json
{
  "training_mode": "lora",
  "artifact_dir": "/data/checkpoints/train_123",
  "training_config": {
    "dataset_version_id": "dsv_123",
    "dataset_domain": "coding",
    "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "training_mode": "lora",
    "epochs": 3,
    "learning_rate": 0.0002,
    "adapter_name": "coding-lora-v1",
    "train_path": "/data/datasets/train.jsonl",
    "validation_path": "/data/datasets/validation.jsonl",
    "test_path": "/data/datasets/test.jsonl",
    "config_path": "/data/checkpoints/train_123/training-config.json"
  }
}
```

The training command must emit JSON like:

```json
{
  "status": "completed",
  "metrics": {
    "loss": 0.1234
  },
  "artifact_path": "/data/checkpoints/train_123",
  "checkpoint_path": "/data/checkpoints/train_123/lora-adapter.bin",
  "log_path": "/data/checkpoints/train_123/training.log",
  "metrics_path": "/data/checkpoints/train_123/metrics.json"
}
```

## Evaluation backend input

The evaluation command receives JSON like:

```json
{
  "training_run": {
    "id": "train_123",
    "dataset_version_id": "dsv_123",
    "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
    "training_mode": "lora",
    "artifact_path": "/data/checkpoints/train_123",
    "training_config": {},
    "metrics": {}
  },
  "dataset_version": {
    "id": "dsv_123",
    "domain": "coding",
    "record_count": 120,
    "train_path": "/data/datasets/train.jsonl",
    "validation_path": "/data/datasets/validation.jsonl",
    "test_path": "/data/datasets/test.jsonl"
  },
  "benchmark_manifest": {
    "benchmark_group": "coding-core"
  },
  "benchmark_records": [
    {
      "benchmark_id": "coding-1",
      "prompt": "Review a small bug fix patch."
    }
  ],
  "frontier_baseline_name": "claude-sonnet-4-6"
}
```

The evaluation command must emit JSON like:

```json
{
  "overall_score": 0.94,
  "record_scores": {
    "coding-1": 0.95
  },
  "package_metadata": {
    "artifact_paths": ["/data/checkpoints/train_123"],
    "domains": ["coding"],
    "task_types": ["code_review"],
    "runtime_targets": ["ollama"]
  }
}
```

`llmProxy` uses `overall_score` for:

- promotion gating
- quality delta vs frontier
- value-per-dollar calculation
- model package quality summary

## Smoke-test adapters

Two example adapters are included for contract testing only:

- [/Volumes/data/development/llmProxy/scripts/example_lora_backend.py](/Volumes/data/development/llmProxy/scripts/example_lora_backend.py)
- [/Volumes/data/development/llmProxy/scripts/example_evaluation_backend.py](/Volumes/data/development/llmProxy/scripts/example_evaluation_backend.py)

These are not real ML backends. They are only meant to validate that:

- the worker can execute a training command
- artifacts are recorded correctly
- the evaluation runner can consume benchmark payloads
- the promotion path is wired correctly

## Example local configuration

```bash
export LLMPROXY_LORA_TRAINER_COMMAND="python3 /Volumes/data/development/llmProxy/scripts/example_lora_backend.py"
export LLMPROXY_QLORA_TRAINER_COMMAND="python3 /Volumes/data/development/llmProxy/scripts/example_lora_backend.py"
export LLMPROXY_EVALUATION_COMMAND="python3 /Volumes/data/development/llmProxy/scripts/example_evaluation_backend.py"
```

Then run the normal workflow:

```bash
python3 -m app.cli training run dsv_123 Qwen/Qwen2.5-Coder-7B-Instruct lora
python3 -m app.cli worker run-once
python3 -m app.cli evaluation run train_123
```

## Real backend examples

Good real backend targets include:

- `mlx_lm.lora` on Apple Silicon
- `peft` + `trl` on CUDA
- a custom evaluation harness that runs benchmark prompts against the trained adapter and produces an aggregate score

The important rule is simple:

- do not emit success JSON unless real work completed
- return a non-zero exit code on failure
- keep the JSON contract stable
