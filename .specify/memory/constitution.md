# llmProxy Constitution

## Purpose

Build a local-first LLM proxy and learning system that converts high-value model interactions into durable local capability.

## Articles

### Article I: Local-First by Default

Sensitive or private work should prefer local routing when feasible.

### Article II: Auditability Over Magic

Requests, routing decisions, evaluations, exports, training runs, and deployments must be inspectable.

### Article III: Quality Gates Before Promotion

No dataset export, model promotion, or deployment happens without explicit validation criteria.

### Article IV: Reversibility Is Mandatory

Routing, promotion, and deployment decisions must support rollback.

### Article V: Separation of Concerns

The proxy serves traffic, the learner builds improved capability, and integration joins them through explicit contracts.

### Article VI: Domain Specialization Over Generality

The first versions optimize for targeted usefulness, not universal breadth.

### Article VII: Deterministic Pipelines Where Possible

Dataset versioning, splitting, manifests, and training configuration should be reproducible.

### Article VIII: Incremental Delivery

Build in phases that preserve a working system at each milestone.

## Non-Negotiable Constraints

- OpenAI-compatible primary chat API
- support for local models and closed teacher models through adapters
- approved and validated data only enters the learner
- rejected, blocked, or secret-bearing records are never exported
- no model promotion without successful evaluation
- no deployment without successful health checks

## Source

This SpecKit constitution is derived from the detailed reference document at `docs/specs/constitution.md`, which remains the extended constitutional reference.
