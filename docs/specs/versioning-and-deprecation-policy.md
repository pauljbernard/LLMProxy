# Versioning and Deprecation Policy

## Purpose

This document defines how APIs, schemas, routing policies, and infrastructure modules evolve over time.

## Versioned Assets

The following assets must be versioned:

- API contracts
- dataset schemas
- event contracts
- routing-policy definitions
- model-registration contracts
- OpenTofu modules
- Kubernetes base manifests

## Semantic Versioning Rule

Use semantic versioning where practical:

- major: incompatible changes
- minor: backward-compatible feature changes
- patch: backward-compatible fixes

## Contract Compatibility Rule

- breaking API or schema changes require a major-version signal or explicit compatibility bridge
- backward-compatible additions may use minor versions
- patch changes must not change meaning

## Deprecation Standard

When deprecating a contract, module, or behavior:

- mark it deprecated in documentation
- identify replacement
- identify earliest removal version
- provide migration guidance

## Minimum Deprecation Notice

For non-emergency removals:

- document the deprecation before removal
- keep the deprecated behavior available for at least one planned release cycle where feasible

## Routing Policy Versioning

Routing policy changes must:

- increment a policy version
- preserve prior versions for audit
- document threshold changes and rationale

## Infrastructure Module Versioning

OpenTofu modules and Kubernetes base manifests should evolve with explicit version notes whenever changes affect:

- required inputs
- outputs
- naming
- resource topology

## Migration Requirement

Breaking schema or contract changes must include:

- migration notes
- compatibility impact
- rollback considerations

## Removal Rule

No supported artifact should be removed silently. Removal requires:

- documented rationale
- operator impact note
- implementation update across affected artifacts
