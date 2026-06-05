# Repository Standard

## Purpose

This document constrains implementation freedom so that different coding agents produce near-identical repository structures, naming patterns, and module boundaries.

## Required Top-Level Layout

The repository must use this top-level structure:

```text
app/
  api/
  proxy/
  providers/
  datasets/
  training/
  evaluation/
  registry/
  deployment/
  integration/
  db/
  schemas/
  services/
  tests/
benchmarks/
scripts/
docs/
  assets/
  specs/
proxy_exports/
datasets/
exports/
models/
checkpoints/
reports/
alembic/
pyproject.toml
README.md
```

Agents may add files within these directories, but may not invent new top-level runtime directories unless the spec pack is updated first.

## Required Python Package Layout

The implementation must use these initial module files:

```text
app/main.py
app/config.py
app/api/openai_compatible.py
app/api/proxy_native.py
app/api/datasets.py
app/api/training.py
app/api/evaluation.py
app/api/models.py
app/api/deployment.py
app/proxy/router.py
app/proxy/classifier.py
app/proxy/policy.py
app/proxy/ensemble.py
app/proxy/judge.py
app/proxy/recorder.py
app/proxy/exporter.py
app/providers/base.py
app/providers/openai_provider.py
app/providers/anthropic_provider.py
app/providers/google_provider.py
app/providers/xai_provider.py
app/providers/bedrock_provider.py
app/providers/azure_openai_provider.py
app/providers/ollama.py
app/providers/vllm.py
app/providers/llama_cpp.py
app/providers/mlx.py
app/datasets/ingestion.py
app/datasets/validation.py
app/datasets/normalization.py
app/datasets/dedupe.py
app/datasets/splitter.py
app/datasets/curriculum.py
app/training/orchestrator.py
app/training/lora_trainer.py
app/training/qlora_trainer.py
app/training/checkpointing.py
app/evaluation/runner.py
app/evaluation/benchmark_loader.py
app/evaluation/judge.py
app/evaluation/code_validation.py
app/evaluation/style_scoring.py
app/evaluation/economics.py
app/registry/model_registry.py
app/registry/artifact_store.py
app/deployment/manager.py
app/deployment/ollama.py
app/deployment/vllm.py
app/deployment/llama_cpp.py
app/deployment/mlx.py
app/integration/events.py
app/integration/outbox.py
app/integration/contracts.py
app/integration/routing_policy.py
app/integration/performance.py
app/db/session.py
app/db/models.py
app/schemas/chat.py
app/schemas/provider.py
app/schemas/routing.py
app/schemas/dataset.py
app/schemas/training.py
app/schemas/evaluation.py
app/schemas/registry.py
app/schemas/integration.py
app/schemas/config.py
app/services/cost.py
app/services/secrets.py
app/services/telemetry.py
```

## Naming Standard

- Use `snake_case` for files, functions, variables, and database columns.
- Use `PascalCase` for Python classes and Pydantic models.
- Use singular nouns for SQLAlchemy model class names.
- Use plural or collection-oriented route names only where the HTTP resource requires them.
- Use explicit names such as `routing_decision`, `training_candidate`, and `dataset_export` instead of vague alternatives such as `job`, `record`, or `item`.

## API Organization

- `openai_compatible.py` owns `POST /v1/chat/completions`, `GET /v1/models`, and `POST /v1/embeddings`.
- `proxy_native.py` owns native proxy orchestration endpoints.
- `datasets.py` owns learner import and dataset inspection endpoints.
- `training.py` owns training-run endpoints.
- `evaluation.py` owns benchmark and evaluation endpoints.
- `models.py` owns model-registry endpoints.
- `deployment.py` owns deployment and rollback endpoints.

Agents may not move these route families into different modules.

## Business Logic Boundaries

- `api/` validates HTTP requests and delegates only.
- `schemas/` contains request, response, and config models only.
- `proxy/` contains runtime routing, classification, judging, recording, and export logic.
- `providers/` contains external provider adapters only.
- `datasets/` contains learner-side dataset processing only.
- `training/` contains training orchestration only.
- `evaluation/` contains evaluation and economics-comparison logic only.
- `registry/` contains model and artifact registration only.
- `deployment/` contains deployment-target operations only.
- `integration/` contains events, contract versions, and routing-policy persistence only.
- `services/` contains cross-cutting helpers such as cost, secrets, and telemetry.

Agents may not collapse these boundaries into a single generic service layer.

## Persistence Standard

- Use Postgres as the system of record.
- Use SQLAlchemy and Alembic.
- Use separate schemas named `proxy`, `learner`, and `integration`.
- Database models must be defined centrally in `app/db/models.py` for the first implementation.
- Migration files must live under `alembic/versions/`.

## Test Layout Standard

The test layout must mirror runtime structure:

```text
app/tests/api/
app/tests/proxy/
app/tests/providers/
app/tests/datasets/
app/tests/training/
app/tests/evaluation/
app/tests/deployment/
app/tests/integration/
```

## Prohibited Variance

Implementation agents must not:

- replace Python/FastAPI with a different runtime stack
- replace Postgres with another primary database
- replace SQLAlchemy/Alembic with unrelated persistence frameworks
- collapse the app into a single file or a small number of oversized modules
- introduce unapproved top-level folders for alternate architectures
- rename canonical modules without updating the spec pack first
