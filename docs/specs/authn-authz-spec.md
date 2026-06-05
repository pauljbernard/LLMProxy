# Authentication and Authorization Specification

## Purpose

This document defines the minimum authentication and authorization model for `llmProxy`.

## Authentication Requirements

The system must support:

- authenticated API access in production
- separate operator and automation credentials
- service-to-service authentication where applicable

## First-Version Authentication Model

The first version may support:

- bearer token authentication for API access
- environment- or secret-backend injected service credentials

## Authorization Tiers

The system should distinguish at least:

- `viewer`
- `operator`
- `deployer`
- `automation`

## Protected Operations

The following operations must require elevated authorization:

- training candidate approval or rejection
- dataset export
- model registration
- deployment promotion
- rollback execution
- routing-policy change
- secret-backend change

## Default Rule

Read access and write access must not be assumed equivalent.

Privileged endpoints must explicitly check authorization tier.

## Service Identities

Cloud deployments should use:

- AWS IAM roles
- GCP Workload Identity
- Azure Managed Identity

Long-lived shared credentials should be minimized.

## Audit Rule

Authenticated identity must be attributable for privileged actions where operationally feasible.
