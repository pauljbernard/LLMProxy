# Runtime Environment Specification

## Purpose

This document defines the canonical runtime dependencies, service contracts, ports, storage paths, and environment variables required to run the system locally or in cloud environments.

## Required Services

Every environment must provide:

- Python 3.11+ application runtime
- Postgres 15+
- Redis 7+
- persistent artifact storage
- outbound internet access for frontier-provider calls when enabled
- optional local model runtime for local-specialist serving

## Required Service Roles

- `api`
- `worker`
- `scheduler`

## Default Internal Ports

- `api`: `8000`
- `learner/admin if separated later`: `8100`
- `postgres`: `5432`
- `redis`: `6379`
- `ollama`: `11434`
- `vllm`: `8001`
- `llama_cpp`: `8080`
- `mlx`: implementation-defined, must be configured explicitly

## Persistent Storage Categories

The runtime must provide persistent storage for:

- dataset exports
- imported datasets
- trained adapters
- checkpoints
- evaluation reports
- benchmark assets

## Canonical Path Variables

- `LLMPROXY_EXPORTS_PATH`
- `LLMPROXY_DATASETS_PATH`
- `LLMPROXY_MODELS_PATH`
- `LLMPROXY_CHECKPOINTS_PATH`
- `LLMPROXY_REPORTS_PATH`

## Required Environment Variables

### Application Core

- `LLMPROXY_ENV`
- `LLMPROXY_LOG_LEVEL`
- `LLMPROXY_API_HOST`
- `LLMPROXY_API_PORT`
- `LLMPROXY_DATABASE_URL`
- `LLMPROXY_REDIS_URL`
- `LLMPROXY_DEFAULT_ROUTE_MODEL`
- `LLMPROXY_BEARER_TOKEN`

### Paths

- `LLMPROXY_EXPORTS_PATH`
- `LLMPROXY_DATASETS_PATH`
- `LLMPROXY_MODELS_PATH`
- `LLMPROXY_CHECKPOINTS_PATH`
- `LLMPROXY_REPORTS_PATH`

### Provider Credentials

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `XAI_API_KEY`
- `AWS_REGION`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`

### Observability

- `LLMPROXY_OTEL_ENABLED`
- `LLMPROXY_OTEL_EXPORTER_ENDPOINT`
- `LLMPROXY_METRICS_NAMESPACE`

### Security and Limits

- `LLMPROXY_REQUEST_TIMEOUT_SECONDS`
- `LLMPROXY_MAX_REQUEST_BYTES`
- `LLMPROXY_RATE_LIMIT_PER_MINUTE`
- `LLMPROXY_SECRET_BACKEND`

## Queue Contracts

Redis-backed queues must at minimum support:

- provider metadata refresh jobs
- dataset import jobs
- training jobs
- evaluation jobs
- deployment jobs
- scheduled KPI aggregation jobs

## Health Checks

Every runtime must expose or support:

- liveness check
- readiness check
- database connectivity check
- Redis connectivity check
- provider configuration sanity check

## GPU Assumptions

Local-model runtimes may require:

- Apple Silicon with MLX
- NVIDIA GPUs for vLLM and QLoRA training
- CPU-only fallback for limited local development

Production deployments must declare whether:

- local inference is enabled
- training is enabled
- GPU-backed workloads are colocated or separate

## Cloud Compatibility Rule

Environment-specific substitution is allowed only at the infrastructure level. Environment variables, logical service roles, and core application behavior must remain consistent across local, AWS, GCP, and Azure.
