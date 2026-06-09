# API Schema Specification

## Purpose

This document defines the canonical request and response shapes for the initial APIs so that multiple implementation agents produce compatible interfaces.

## OpenAI-Compatible Chat Endpoint

Endpoint:

- `POST /v1/chat/completions`

Minimum request fields:

```json
{
  "model": "proxy-auto",
  "messages": [
    {
      "role": "user",
      "content": "string"
    }
  ],
  "stream": false,
  "temperature": 0.2,
  "max_tokens": 1024,
  "metadata": {
    "session_id": "sess_123",
    "domain_hint": "coding",
    "task_type_hint": "bug_fix"
  }
}
```

Required request rules:

- `model` is required
- `messages` is required and non-empty
- `stream` defaults to `false`
- `metadata.session_id` is required for non-anonymous routed sessions in the first implementation

Minimum non-streaming response fields:

```json
{
  "id": "chatcmpl_123",
  "object": "chat.completion",
  "created": 1780651200,
  "model": "proxy-auto",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "string"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 120,
    "completion_tokens": 300,
    "total_tokens": 420
  }
}
```

## Native Routing-Decision Record

This object must be persisted and may also be returned from debug or inspection endpoints.

```json
{
  "routing_decision_id": "route_123",
  "session_id": "sess_123",
  "request_id": "req_123",
  "policy_version": "1.0.0",
  "selected_provider": "openai",
  "selected_provider_family": "OpenAI",
  "selected_model": "gpt-x",
  "selected_mode": "frontier_single",
  "ranked_alternatives": [
    {
      "rank": 1,
      "provider": "openai",
      "model": "gpt-x",
      "score": 0.91
    },
    {
      "rank": 2,
      "provider": "ollama",
      "model": "qwen2.5-coder:14b",
      "score": 0.78
    }
  ],
  "decision_rationale": "Selected frontier model for architecture task with high complexity.",
  "predicted_cost_class": "high",
  "predicted_latency_class": "medium",
  "fallback_chain": [
    {
      "order": 1,
      "provider": "anthropic",
      "model": "claude-x"
    },
    {
      "order": 2,
      "provider": "ollama",
      "model": "qwen2.5:32b"
    }
  ]
}
```

## Training Candidate Schema

Minimum canonical fields:

```json
{
  "candidate_id": "cand_123",
  "request_id": "req_123",
  "session_id": "sess_123",
  "domain": "coding",
  "task_type": "bug_fix",
  "status": "captured",
  "quality_score": 0.87,
  "approval_status": "needs_review",
  "export_eligible": false,
  "selected_response": "string",
  "messages": [],
  "provenance": {},
  "validation": {},
  "metadata": {}
}
```

## Native Teacher Ensemble Endpoint

Endpoint:

- `POST /proxy/ensemble`

Request shape:

- identical to the canonical `POST /v1/chat/completions` request
- `model` should be `proxy-ensemble` or a teacher-oriented alias

Minimum response shape:

```json
{
  "response": {
    "id": "chatcmpl_123",
    "object": "chat.completion",
    "created": 1780651200,
    "model": "proxy-ensemble",
    "choices": [],
    "usage": {}
  },
  "teacher_candidates": [
    {
      "response_id": "resp_1",
      "provider": "anthropic",
      "provider_family": "Anthropic",
      "model": "claude-sonnet-4-6",
      "content": "string",
      "score": 0.95,
      "rationale": "string"
    }
  ],
  "judge_critique": {
    "judge_provider": "rule_based_judge",
    "judge_model": "heuristic-v1",
    "selected_response_id": "resp_1",
    "selected_provider": "anthropic",
    "selected_model": "claude-sonnet-4-6",
    "rationale": "string",
    "scores": {
      "resp_1": 0.98
    }
  }
}
```

## Training Candidate Review Endpoints

Endpoints:

- `GET /proxy/training-candidates`
- `POST /proxy/training-candidates/{id}/approve`
- `POST /proxy/training-candidates/{id}/reject`

Representative list item:

```json
{
  "id": "cand_123",
  "request_log_id": "req_123",
  "routing_decision_id": "route_123",
  "session_id": "sess_123",
  "domain": "coding",
  "task_type": "code_review",
  "status": "needs_review",
  "quality_score": 0.86,
  "approval_status": "needs_review",
  "export_eligible": false,
  "selected_response": "string",
  "metadata": {
    "selected_provider": "ollama",
    "selected_model": "qwen2.5-coder:14b"
  }
}
```

Representative approve/reject response:

```json
{
  "candidate_id": "cand_123",
  "status": "approved",
  "approval_status": "approved",
  "export_eligible": true
}
```

## Dataset Export Endpoint

Endpoint:

- `POST /proxy/export/jsonl`

Request shape:

```json
{
  "domain": "coding",
  "name": "coding-adapter",
  "min_quality_score": 0.5
}
```

Response shape:

```json
{
  "dataset_export_id": "dsexp_123",
  "manifest_path": "/data/exports/coding-adapter-dsexp_123.manifest.json",
  "data_path": "/data/exports/coding-adapter-dsexp_123.jsonl",
  "record_count": 12
}
```

## Dataset Import Request

Endpoint:

- `POST /datasets/import`

Request shape:

```json
{
  "dataset_export_id": "dsexp_123",
  "manifest_path": "/proxy_exports/domain.manifest.json",
  "data_path": "/proxy_exports/domain.jsonl"
}
```

Representative import response:

```json
{
  "dataset_export_id": "dsexp_123",
  "dataset_import_id": "dsimp_123",
  "dataset_version_id": "dsv_123",
  "status": "imported",
  "record_count": 42
}
```

## Training Run Endpoints

Endpoints:

- `POST /training/runs`
- `GET /training/runs`

Training submission request shape:

```json
{
  "dataset_version_id": "dsv_123",
  "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
  "training_mode": "lora",
  "epochs": 3,
  "learning_rate": 0.0002,
  "adapter_name": "coding-lora-v1"
}
```

Training submission response shape:

```json
{
  "training_run_id": "train_123",
  "dataset_version_id": "dsv_123",
  "training_mode": "lora",
  "status": "completed",
  "artifact_path": "/data/checkpoints/train_123/adapter-lora.bin",
  "metrics": {
    "loss": 0.18,
    "epochs": 3,
    "learning_rate": 0.0002,
    "mode": "lora",
    "checkpoint_path": "/data/checkpoints/train_123/checkpoint-lora.txt",
    "log_path": "/data/checkpoints/train_123/training.log",
    "metrics_path": "/data/checkpoints/train_123/metrics.json"
  }
}
```

Representative training run list item:

```json
{
  "id": "train_123",
  "dataset_version_id": "dsv_123",
  "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
  "training_mode": "lora",
  "status": "completed",
  "artifact_path": "/data/checkpoints/train_123/adapter-lora.bin",
  "metrics": {
    "loss": 0.18,
    "epochs": 3,
    "learning_rate": 0.0002,
    "mode": "lora"
  }
}
```

## Evaluation Run Endpoints

Endpoints:

- `POST /evaluation/runs`
- `GET /evaluation/runs`

Evaluation submission request shape:

```json
{
  "training_run_id": "train_123",
  "frontier_baseline_name": "claude-sonnet-4-6"
}
```

Evaluation submission response shape:

```json
{
  "evaluation_run_id": "eval_123",
  "training_run_id": "train_123",
  "domain": "coding",
  "frontier_baseline_name": "claude-sonnet-4-6",
  "overall_score": 0.9,
  "quality_delta_vs_frontier": 0.02,
  "value_per_dollar_gain_vs_frontier": 4.1,
  "promotion_status": "approved",
  "package_manifest_path": "/data/models/train_123/model-package.json",
  "result": {
    "promotion_status": "approved",
    "gate_failures": []
  }
}
```

Representative evaluation run list item:

```json
{
  "id": "eval_123",
  "training_run_id": "train_123",
  "domain": "coding",
  "frontier_baseline_name": "claude-sonnet-4-6",
  "overall_score": 0.9,
  "quality_delta_vs_frontier": 0.02,
  "value_per_dollar_gain_vs_frontier": 4.1,
  "promotion_status": "approved",
  "package_manifest_path": "/data/models/train_123/model-package.json"
}
```

## KPI Report Endpoint

Endpoint:

- `GET /evaluation/kpis`

Representative response:

```json
{
  "report_path": "/data/reports/kpi-report-latest.json",
  "metrics": [
    {
      "time_window": "all_time",
      "metric_name": "avoided_frontier_spend",
      "metric_value": 0.1192,
      "formula_version": "1.0",
      "policy_version": "rpol_123",
      "sample_size": 1,
      "currency": "USD",
      "estimation_flag": true
    }
  ]
}
```

## Local Model Registry Endpoint

Endpoint:

- `GET /models/local`

Representative list item:

```json
{
  "model_registry_id": "model_train_123",
  "model_alias": "coding-lora-train_123",
  "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
  "adapter_type": "lora",
  "artifact_paths": ["/data/checkpoints/train_123/adapter-lora.bin"],
  "domains": ["coding"],
  "promotion_status": "approved"
}
```

## Deployment Endpoints

Endpoints:

- `POST /deployment/models/{model_alias}/activate`
- `POST /deployment/models/{model_alias}/rollback`
- `GET /deployment/routing-policies`

Deployment activation request shape:

```json
{
  "deployment_mode": "production",
  "domains": ["coding"],
  "task_types": ["code_review"],
  "canary_percent": 1.0
}
```

Deployment response shape:

```json
{
  "model_alias": "coding-lora-v1",
  "deployment_mode": "production",
  "status": "deployed",
  "policy_version": "rpol_123",
  "runtime": "ollama",
  "endpoint_url": "http://localhost:11434"
}
```

Representative routing policy list item:

```json
{
  "id": "rpol_123",
  "policy_version": "rpol_123",
  "policy": {
    "entries": [
      {
        "model_alias": "coding-lora-v1",
        "deployment_mode": "production",
        "runtime": "ollama",
        "provider_key": "local:coding-lora-v1",
        "domains": ["coding"],
        "task_types": ["code_review"],
        "canary_percent": 0.0
      }
    ]
  }
}
```

## Model Registration Request

Endpoint:

- `POST /proxy/models/register`

Request shape:

```json
{
  "model_registry_id": "model_123",
  "model_alias": "coding-local-v1",
  "base_model": "Qwen/Qwen2.5-Coder-14B-Instruct",
  "adapter_type": "lora",
  "adapter_path": "/models/adapters/coding-local-v1",
  "runtime": "ollama",
  "endpoint_url": "http://localhost:11434",
  "domains": ["coding"],
  "task_types": ["bug_fix", "code_review"],
  "quality": {
    "overall_score": 0.88,
    "domain_scores": {
      "coding": 0.90
    }
  },
  "status": "candidate"
}
```

## Error Envelope

All native endpoints should use this minimum error envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Human-readable error message",
    "details": {}
  }
}
```
