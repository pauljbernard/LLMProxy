# Build Read Order

## Purpose

This document defines the required reading order for implementation agents so critical constraints are not missed.

## Mandatory Read Order For All Implementation Work

1. `docs/specs/spec-precedence.md`
2. `.specify/memory/constitution.md`
3. `specs/001-llmproxy-foundation/spec.md`
4. `specs/001-llmproxy-foundation/plan.md`
5. `specs/001-llmproxy-foundation/tasks.md`
6. `docs/specs/agent-handoff.md`
7. `docs/specs/repository-standard.md`
8. `docs/specs/implementation-charter.md`
9. `docs/specs/requirements.md`
10. `docs/specs/system-specification.md`
11. `docs/specs/acceptance-criteria.md`

## Mandatory Contract Read Order

1. `docs/contracts/openapi.yaml`
2. `docs/contracts/schemas/*.json`
3. `docs/specs/api-schema-spec.md`
4. `docs/specs/database-schema-spec.md`
5. `alembic/versions/*.py`

## Mandatory Infrastructure Read Order

1. `docs/specs/deployment-architecture.md`
2. `docs/specs/runtime-environment-spec.md`
3. `docs/specs/iac-standard.md`
4. `docs/specs/deployment-manifest-standard.md`
5. `docs/specs/kubernetes-base-spec.md`
6. `docs/specs/compose-spec.md`
7. `docs/specs/opentofu-module-spec.md`
8. `infra/`

## Mandatory Security Read Order

1. `docs/specs/security-operations-spec.md`
2. `docs/specs/threat-model.md`
3. `docs/specs/authn-authz-spec.md`
4. `docs/specs/secret-rotation-and-key-management-spec.md`
5. `docs/specs/supply-chain-security-spec.md`
6. `docs/specs/security-incident-response-spec.md`

## Task-Specific Reads

- routing work: `routing-policy-spec.md`, `provider-strategy.md`, `metrics-spec.md`
- training/data work: `data-contracts.md`, `data-governance-spec.md`, `model-package-spec.md`
- evaluation work: `benchmark-artifact-spec.md`, `economics-and-kpis.md`, `test-strategy.md`
- CI/CD and infra work: `ci-cd-spec.md`, `engineering-workflow-standard.md`
