# Product Overview

`llmProxy` is a local-first LLM routing and learning system.

It sits between your applications and multiple model providers, captures high-value interactions, and turns approved examples into domain-specific local specialists that can gradually take eligible traffic away from frontier models.

## What It Does

- Exposes an OpenAI-compatible proxy surface for chat, embeddings, and model discovery.
- Routes requests across local and frontier model providers.
- Captures requests, routing decisions, model responses, and training candidates.
- Supports teacher ensemble workflows for high-value prompts.
- Exports approved examples into fine-tuning-ready datasets.
- Imports, validates, versions, and splits datasets for training.
- Orchestrates training, evaluation, promotion, deployment, rollback, and KPI reporting.
- Gives operators a CLI and browser-based console for runtime control and monitoring.

## Who It Is For

- Platform engineers running an internal model gateway
- AI engineers building domain-specific local specialists
- Operators who need transparent routing, auditable actions, and troubleshooting visibility

## Primary Objective

The primary objective is to reduce repeated frontier token spend by shifting eligible workloads to smaller, cheaper, domain-specialized local models without giving up observability, policy control, or evaluation discipline.

## Main Surfaces

- Application/API: `http://127.0.0.1:8000`
- Operator console: `http://127.0.0.1:8000/admin`
- Admin CLI: `python3 -m app.cli ...`

## Typical Lifecycle

1. Route real traffic through the proxy.
2. Capture and review candidate interactions.
3. Export approved examples.
4. Import and version datasets.
5. Train a specialist.
6. Evaluate it against baseline behavior.
7. Deploy it in shadow, canary, or production mode.
8. Monitor substitution, errors, performance, and economics.
