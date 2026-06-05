# Database Schema Specification

## Purpose

This document defines the canonical first-pass database entities so that multiple agents do not invent materially different persistence models.

## Schema Names

The database must use these schemas:

- `proxy`
- `learner`
- `integration`

## Proxy Tables

### `proxy.request_log`

Required columns:

- `id`
- `session_id`
- `external_request_id`
- `requested_model`
- `domain`
- `task_type`
- `complexity`
- `privacy_level`
- `request_json`
- `created_at`

### `proxy.routing_decision`

Required columns:

- `id`
- `request_log_id`
- `session_id`
- `policy_version`
- `selected_provider`
- `selected_provider_family`
- `selected_model`
- `selected_mode`
- `decision_rationale`
- `predicted_cost_class`
- `predicted_latency_class`
- `ranked_alternatives_json`
- `fallback_chain_json`
- `created_at`

### `proxy.model_response`

Required columns:

- `id`
- `request_log_id`
- `provider`
- `provider_family`
- `model`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `cost_estimate`
- `finish_reason`
- `response_json`
- `created_at`

### `proxy.training_candidate`

Required columns:

- `id`
- `request_log_id`
- `routing_decision_id`
- `session_id`
- `domain`
- `task_type`
- `status`
- `quality_score`
- `approval_status`
- `export_eligible`
- `selected_response`
- `messages_json`
- `provenance_json`
- `validation_json`
- `metadata_json`
- `created_at`
- `updated_at`

### `proxy.dataset_export`

Required columns:

- `id`
- `domain`
- `dataset_export_id`
- `manifest_path`
- `data_path`
- `record_count`
- `sha256`
- `schema_version`
- `created_at`

### `proxy.model_registry`

Required columns:

- `id`
- `model_registry_id`
- `model_alias`
- `provider`
- `runtime`
- `base_model`
- `adapter_type`
- `adapter_path`
- `status`
- `quality_json`
- `domains_json`
- `task_types_json`
- `created_at`
- `updated_at`

## Learner Tables

### `learner.dataset_import`

Required columns:

- `id`
- `dataset_export_id`
- `manifest_path`
- `data_path`
- `status`
- `record_count`
- `quarantined_count`
- `created_at`

### `learner.dataset_version`

Required columns:

- `id`
- `domain`
- `version_name`
- `source_import_id`
- `train_path`
- `validation_path`
- `test_path`
- `record_count`
- `created_at`

### `learner.training_run`

Required columns:

- `id`
- `dataset_version_id`
- `base_model`
- `training_mode`
- `status`
- `training_config_json`
- `metrics_json`
- `artifact_path`
- `started_at`
- `completed_at`

### `learner.evaluation_run`

Required columns:

- `id`
- `training_run_id`
- `domain`
- `frontier_baseline_name`
- `overall_score`
- `quality_delta_vs_frontier`
- `value_per_dollar_gain_vs_frontier`
- `result_json`
- `created_at`

## Integration Tables

### `integration.integration_event`

Required columns:

- `id`
- `event_id`
- `event_type`
- `source`
- `payload_json`
- `occurred_at`
- `processed_at`

### `integration.routing_policy_version`

Required columns:

- `id`
- `policy_version`
- `policy_json`
- `created_at`

### `integration.model_performance_sample`

Required columns:

- `id`
- `model_alias`
- `domain`
- `request_log_id`
- `route_type`
- `cost_estimate`
- `quality_score`
- `successful`
- `created_at`

## ORM Standard

- Use UUID or string identifiers consistently across all core tables.
- Use `created_at` and `updated_at` timestamps where mutation history matters.
- Store structured contract payloads in `jsonb` columns with canonical field names matching the spec pack.
- Do not split these core entities into unrelated micro-tables in the first implementation.
