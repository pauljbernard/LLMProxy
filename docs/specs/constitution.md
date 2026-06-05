# Project Constitution

## Purpose

Build a local-first LLM proxy and learning system that converts high-value model interactions into durable local capability.

The system exists to:

1. Expose an OpenAI-compatible runtime proxy for local models, teacher models, coding agents, IDEs, CLIs, and related tools.
2. Capture, validate, export, train, evaluate, and redeploy improved local models through a controlled learning loop.

## Primary Outcome

The project is not intended to produce a frontier foundation model.

The intended outcome is smaller, cheaper, private, local, domain-specialized models that improve over time from:

- teacher-model expertise
- validated runtime interactions
- repository-specific patterns
- personal coding and architecture preferences
- Common Lisp and Smalltalk knowledge
- agent-system design patterns
- investment reasoning frameworks
- writing and explanation style

## Constitutional Principles

1. Local-first by default
   Sensitive or private work should prefer local routing when feasible.
2. Auditability over magic
   Requests, routing decisions, evaluations, exports, training runs, and deployments must be inspectable.
3. Quality gates before promotion
   No dataset export, model promotion, or deployment happens without explicit validation criteria.
4. Reversibility is mandatory
   Routing, promotion, and deployment decisions must support rollback.
5. Separation of runtime and learner concerns
   The proxy serves traffic; the learner builds improved capability; integration joins them through explicit contracts.
6. Domain specialization over generality
   The first versions should optimize for targeted usefulness, not universal breadth.
7. Deterministic pipelines where possible
   Dataset versioning, splitting, manifests, and training configuration should be reproducible.
8. Incremental delivery
   Build in phases that preserve a working system at each milestone.

## Non-Negotiable Constraints

- The proxy must remain OpenAI-compatible for the primary chat API.
- The system must support both local models and closed teacher models through adapters.
- Training data must not enter the learner unless approved and validated.
- Rejected, blocked, or secret-bearing records must never be exported.
- A trained model may not be promoted unless evaluation succeeds.
- A model may not be deployed unless deployment health checks succeed.

## First-Version Non-Goals

The first implementation does not need to:

- train frontier-scale models
- support distributed multi-node training
- implement RLHF or full preference optimization
- support every provider or every training framework
- replace a complete MLOps platform
- make autonomous financial decisions
- execute financial transactions
- guarantee factual correctness without validation
- deliver enterprise-grade multi-user security

## Success Standard

The system is successful when it behaves as a reliable, auditable, reversible, self-improving learning loop rather than a simple API wrapper or isolated fine-tuning pipeline.
