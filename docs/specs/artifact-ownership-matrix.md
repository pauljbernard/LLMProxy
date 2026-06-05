# Artifact Ownership Matrix

## Purpose

This matrix identifies the primary source of truth for each concern so overlapping documents do not drift.

| Concern | Primary Source of Truth | Secondary References |
|---|---|---|
| repo structure | `repository-standard.md` | `implementation-charter.md` |
| implementation behavior constraints | `implementation-charter.md` | `agent-handoff.md` |
| API endpoint contract | `docs/contracts/openapi.yaml` | `api-schema-spec.md` |
| JSON payload shape | `docs/contracts/schemas/*.json` | `api-schema-spec.md` |
| database schema | `alembic/versions/*.py` | `database-schema-spec.md` |
| routing policy behavior | `routing-policy-spec.md` | `requirements.md`, `system-specification.md` |
| provider coverage | `provider-strategy.md` | `requirements.md` |
| KPI formulas | `metrics-spec.md` | `economics-and-kpis.md` |
| benchmark artifact format | `benchmark-artifact-spec.md` | `system-specification.md` |
| model package metadata | `model-package-spec.md` | `registry-interoperability-spec.md` |
| provenance and licensing metadata | `asset-provenance-and-licensing-spec.md` | `data-governance-spec.md` |
| deployment topology | `deployment-architecture.md` | `infrastructure-mapping.md` |
| runtime env vars and ports | `runtime-environment-spec.md` | `compose-spec.md` |
| local compose manifest | `infra/compose/docker-compose.yml` | `compose-spec.md` |
| kubernetes base manifests | `infra/kubernetes/base/*` | `kubernetes-base-spec.md` |
| OpenTofu structure | `infra/tofu/` | `iac-standard.md`, `opentofu-module-spec.md` |
| security controls | `security-control-matrix.md` | security-related specs |
| test obligations | `critical-path-test-matrix.md` | `test-strategy.md` |
| workflow and release discipline | `engineering-workflow-standard.md` | `ci-cd-spec.md` |
