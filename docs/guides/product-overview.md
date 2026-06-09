# Product Overview

`llmProxy` is a local-first LLM routing and learning system.

It sits between your applications and multiple model providers, captures high-value interactions, and turns approved examples into domain-specific local specialists that can gradually take eligible traffic away from frontier models.

The important framing is that `llmProxy` is more than just a proxy:

- it is a training proxy that converts repeated model usage into reusable learning assets
- it is a cost-reduction strategy for organizations that want to move suitable workloads from expensive frontier inference to cheaper specialized local models
- it is an intellectual-property retention strategy, because valuable prompts, responses, routing decisions, prompt rollouts, and approved exemplars remain inside your control plane instead of disappearing into transient API calls

## What It Does

- Exposes an OpenAI-compatible proxy surface for chat, embeddings, and model discovery.
- Routes requests across local and frontier model providers.
- Captures requests, routing decisions, model responses, and training candidates.
- Supports teacher ensemble workflows for high-value prompts.
- Exports approved examples into fine-tuning-ready datasets.
- Imports, validates, versions, and splits datasets for training.
- Orchestrates training, evaluation, promotion, deployment, rollback, and KPI reporting.
- Gives operators a CLI and browser-based console for runtime control and monitoring.

## Why It Exists

Most LLM gateways stop at routing, auth, and observability. `llmProxy` goes further by making production traffic part of a deliberate learning loop.

That matters for two reasons:

1. Cost discipline

- repeated high-value work should not stay permanently dependent on the most expensive foundation-model path if a smaller specialist can eventually perform it well enough
- the proxy helps measure where frontier usage is valuable, where it is repetitive, and where it is a candidate for substitution

2. Capability ownership

- prompts, approved responses, evaluation signals, and learned adapters are strategic assets
- `llmProxy` helps retain those assets as internal capability instead of outsourcing them indefinitely to vendor APIs

The result is a system that can start as a safe frontier gateway and evolve into a model-substitution and specialization platform.

## Who It Is For

- Platform engineers running an internal model gateway
- AI engineers building domain-specific local specialists
- Operators who need transparent routing, auditable actions, and troubleshooting visibility

## Primary Objective

The primary objective is to reduce repeated frontier token spend by shifting eligible workloads to smaller, cheaper, domain-specialized local models without giving up observability, policy control, or evaluation discipline.

## Unique Value Proposition

`llmProxy` combines four roles that are often split across separate products:

- gateway: a drop-in front door for tools, CLIs, IDEs, and services
- router: policy-driven selection across frontier and local runtimes
- training pipeline: candidate capture, export, dataset versioning, training, and evaluation
- control plane: observability, prompt rollout, governance, readiness, and runtime operations

That combination is what makes it a training proxy rather than only an inference proxy.

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
