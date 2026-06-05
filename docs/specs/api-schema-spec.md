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
