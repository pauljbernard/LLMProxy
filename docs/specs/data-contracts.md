# Data Contracts

## Dataset Export Contract

Approved training candidates are exported as JSONL. Each line is a complete training record.

Required top-level fields:

- `schema_version`
- `candidate_id`
- `domain`
- `task_type`
- `messages`
- `selected_response`
- `quality_score`
- `approval_status`
- `export_eligible`
- `provenance`
- `validation`
- `metadata`

Example record:

```json
{
  "schema_version": "1.0",
  "candidate_id": "cand_20260605_8821c",
  "domain": "software_architecture",
  "task_type": "architecture_decision",
  "messages": [
    {
      "role": "system",
      "content": "You are a senior software architect."
    },
    {
      "role": "user",
      "content": "Should this system use Neo4j or Postgres with pgvector?"
    },
    {
      "role": "assistant",
      "content": "The better default is Postgres with pgvector unless..."
    }
  ],
  "selected_response": "The better default is Postgres with pgvector unless...",
  "quality_score": 0.93,
  "approval_status": "approved",
  "export_eligible": true,
  "provenance": {
    "request_id": "req_20260605_9f21a",
    "source": "teacher_ensemble",
    "teacher_models": [
      "teacher_reasoning_primary",
      "teacher_coding_primary"
    ],
    "judge_model": "teacher_reasoning_primary",
    "created_at": "2026-06-05T10:15:00Z"
  },
  "validation": {
    "validated": true,
    "validation_type": "judge_and_rules",
    "tests_passed": null,
    "static_checks_passed": null,
    "secrets_detected": false
  },
  "metadata": {
    "style_tags": [
      "causal",
      "technical",
      "tradeoff_oriented"
    ],
    "target_adapter": "architecture",
    "privacy_level": "normal"
  }
}
```

Initial export targets:

- `architecture-adapter.jsonl`
- `coding-adapter.jsonl`
- `common-lisp-adapter.jsonl`
- `smalltalk-adapter.jsonl`
- `agent-systems-adapter.jsonl`
- `investment-analysis-adapter.jsonl`
- `writing-style-adapter.jsonl`

## Dataset Export Manifest

Each export must include a manifest with at least:

- `schema_version`
- `dataset_export_id`
- `name`
- `domain`
- `created_at`
- `record_count`
- `source_system`
- `export_file`
- `sha256`
- `min_quality_score`
- `candidate_status`
- `schema_versions`
- `compatible_learner_versions`

The learner must reject an export if:

- the manifest is missing
- the checksum does not match
- the schema version is unsupported
- the record count does not match
- required fields are missing

## Dataset Import Contract

Initial learner import endpoint:

- `POST /datasets/import`

Example request:

```json
{
  "dataset_export_id": "dsexp_20260605_772ab",
  "manifest_path": "/proxy_exports/architecture-adapter-20260605.manifest.json",
  "data_path": "/proxy_exports/architecture-adapter-20260605.jsonl"
}
```

Validation rules:

- record must contain messages
- messages must contain user and assistant turns
- assistant response must be non-empty
- metadata must contain domain
- metadata must contain task type
- quality score must meet threshold
- approval status must be `approved`
- export eligible must be `true`
- record must not be rejected or blocked

Optional validation:

- secret detection
- API key detection
- credential detection
- private key detection
- malformed code fence detection
- token limit enforcement

## Model Provider Contract

All providers implement a normalized interface that supports:

- chat requests
- streaming chat requests
- embeddings
- model listing

Normalized response metadata includes:

- `model`
- `provider`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `cost_estimate`
- `finish_reason`
- `raw_response_reference`

## Model Registration Contract

Proxy registration endpoint:

- `POST /proxy/models/register`

Representative payload fields:

- `model_registry_id`
- `model_alias`
- `base_model`
- `adapter_type`
- `adapter_path`
- `runtime`
- `endpoint_url`
- `domains`
- `task_types`
- `quality`
- `status`
- `created_at`

## Event Contract

Recommended first implementation:

- Postgres outbox table with polling

Future options:

- Redis Streams
- Kafka
- NATS

Initial event types:

- `candidate.approved`
- `dataset.exported`
- `dataset.imported`
- `training.started`
- `training.completed`
- `training.failed`
- `evaluation.completed`
- `model.approved`
- `model.deployed`
- `model.registered`
- `model.rolled_back`
- `routing.updated`

Example event:

```json
{
  "event_id": "evt_20260605_abc99",
  "event_type": "dataset.exported",
  "occurred_at": "2026-06-05T10:31:00Z",
  "source": "llm-proxy-foundry",
  "payload": {
    "dataset_export_id": "dsexp_20260605_772ab",
    "manifest_path": "/proxy_exports/architecture-adapter-20260605.manifest.json",
    "data_path": "/proxy_exports/architecture-adapter-20260605.jsonl"
  }
}
```

## Version Compatibility Contract

Every exported dataset must declare:

- `schema_version`
- `source_proxy_version`
- `compatible_learner_versions`

Every registered model must declare:

- `model_contract_version`
- `learner_version`
- `compatible_proxy_versions`

Compatibility rules:

- same major version required
- minor version may be backward compatible
- patch version is compatible

Receiving systems must reject incompatible payloads.
