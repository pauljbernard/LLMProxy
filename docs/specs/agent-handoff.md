# Agent Handoff

## Purpose

This document is for future coding agents that will implement the proxy from the specification set in this repository.

## Required Inputs

Before implementation, treat these documents as the primary source of truth:

- `.specify/memory/constitution.md`
- `specs/001-llmproxy-foundation/spec.md`
- `specs/001-llmproxy-foundation/plan.md`
- `specs/001-llmproxy-foundation/tasks.md`
- `specs/001-llmproxy-foundation/research.md`
- `specs/001-llmproxy-foundation/data-model.md`
- `specs/001-llmproxy-foundation/quickstart.md`
- `docs/specs/requirements.md`
- `docs/specs/system-specification.md`
- `docs/specs/data-contracts.md`
- `docs/specs/provider-strategy.md`
- `docs/specs/routing-policy-spec.md`
- `docs/specs/economics-and-kpis.md`
- `docs/specs/metrics-spec.md`
- `docs/specs/domain-specialization-plan.md`
- `docs/specs/glossary.md`
- `docs/specs/repository-standard.md`
- `docs/specs/implementation-charter.md`
- `docs/specs/api-schema-spec.md`
- `docs/specs/database-schema-spec.md`
- `docs/specs/deployment-architecture.md`
- `docs/specs/runtime-environment-spec.md`
- `docs/specs/container-and-release-standard.md`
- `docs/specs/cloud-operations-runbook.md`
- `docs/specs/security-operations-spec.md`
- `docs/specs/infrastructure-mapping.md`
- `docs/specs/iac-standard.md`
- `docs/specs/deployment-manifest-standard.md`
- `docs/specs/kubernetes-base-spec.md`
- `docs/specs/compose-spec.md`
- `docs/specs/opentofu-module-spec.md`
- `docs/specs/cloud-terraform-mapping.md`
- `docs/specs/engineering-workflow-standard.md`
- `docs/specs/test-strategy.md`
- `docs/specs/ci-cd-spec.md`
- `docs/specs/data-governance-spec.md`
- `docs/specs/versioning-and-deprecation-policy.md`
- `docs/specs/model-package-spec.md`
- `docs/specs/asset-provenance-and-licensing-spec.md`
- `docs/specs/benchmark-artifact-spec.md`
- `docs/specs/registry-interoperability-spec.md`
- `docs/specs/threat-model.md`
- `docs/specs/authn-authz-spec.md`
- `docs/specs/security-incident-response-spec.md`
- `docs/specs/supply-chain-security-spec.md`
- `docs/specs/secret-rotation-and-key-management-spec.md`
- `docs/specs/build-read-order.md`
- `docs/specs/artifact-ownership-matrix.md`
- `docs/specs/performance-slo-spec.md`
- `docs/specs/capacity-planning-spec.md`
- `docs/specs/phase-1-implementation-checklist.md`
- `docs/specs/implementation-review-gates.md`
- `docs/specs/critical-path-test-matrix.md`
- `docs/specs/security-control-matrix.md`
- `docs/specs/deployment-profile-matrix.md`
- `docs/specs/operator-playbooks.md`
- `docs/specs/day-0-day-1-day-2-ops.md`
- `docs/specs/control-surface-minimization-spec.md`
- `docs/specs/default-config-profile-spec.md`
- `docs/specs/quickstart-paths.md`
- `docs/specs/minimum-viable-adoption-spec.md`
- `docs/specs/persona-based-adoption-guide.md`
- `docs/specs/prerequisites-matrix.md`
- `docs/specs/time-to-first-value-spec.md`
- `docs/specs/feature-gating-matrix.md`
- `docs/specs/coding-agent-iteration-protocol.md`
- `docs/specs/implementation-session-template.md`
- `docs/specs/progress-report-template.md`
- `docs/specs/clarification-and-decision-log-spec.md`
- `docs/specs/iteration-planning-standard.md`
- `docs/specs/engineer-agent-collaboration-spec.md`
- `docs/specs/branch-lifecycle-spec.md`
- `docs/specs/pr-management-spec.md`
- `docs/specs/multi-session-implementation-spec.md`
- `docs/specs/implementation-plan.md`
- `docs/specs/acceptance-criteria.md`

Reference baseline:

- `baseline.txt`

## Implementation Expectations

The implementation agent must:

- preserve OpenAI compatibility for primary chat usage
- implement the system incrementally by phase
- avoid skipping quality gates just to make the system appear complete
- keep runtime, learner, and integration contracts explicit
- prefer deterministic, inspectable flows over hidden heuristics
- keep model routing and promotion reversible
- avoid unauthorized architecture changes, schema drift, or module renaming
- report progress after each bounded implementation iteration

## Suggested First Build Slice

The recommended first coding slice is:

1. repository structure
2. configuration loader
3. canonical database schema and migrations
4. normalized provider, chat, and routing-decision schemas
5. one local provider adapter
6. at least two frontier-provider adapters
7. `POST /v1/chat/completions`
8. request, response, and routing-decision logging
9. simple routing aliases
10. provider capability registry and pricing metadata support

That slice should produce a usable minimal runtime proxy before ensemble, training, or deployment automation is added.

## Guardrails

- Do not implement learner features before contracts for exports and imports are in place.
- Do not promote models without evaluation persistence.
- Do not export records that are rejected, blocked, or secret-bearing.
- Do not hide routing decisions; persist enough metadata to audit behavior.
- Do not collapse the entire baseline into one giant module or one giant prompt.
- Do not improvise beyond the repository, API, DB, metrics, and routing standards defined in this specification set.

## Deliverable Shape

Future implementation work should leave behind:

- executable code
- migration files
- tests
- configuration examples
- benchmark fixtures where applicable
- operator documentation for local startup and evaluation
- decision-log updates when clarification materially changes implementation

## Handoff Completion Standard

An implementation handoff is considered successful when a coding agent can start Phase 1 directly from this specification set without needing to reinterpret the project’s purpose, architecture, contracts, or delivery order.
