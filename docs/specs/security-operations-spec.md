# Security Operations Specification

## Purpose

This document defines the minimum production security expectations for local and cloud operation.

## Core Requirements

The system must support:

- TLS in production
- secret storage outside source code
- least-privilege access for runtime services
- audit logging for privileged actions
- separation of operator and application credentials
- encrypted storage for managed databases and artifact stores where supported

## Secret Management

Preferred secret backends:

- local: environment variables or local secret store
- AWS: Secrets Manager or SSM Parameter Store
- GCP: Secret Manager
- Azure: Key Vault

Secrets must include:

- provider API keys
- bearer tokens
- database credentials where not using identity-based auth
- Redis credentials where applicable

## Identity and Access

Preferred identity patterns:

- AWS: IAM roles for tasks or service accounts
- GCP: Workload Identity
- Azure: Managed Identity

Long-lived static cloud credentials should be avoided where identity-based access is available.

## Network Security

- public access is allowed only to ingress endpoints
- Postgres and Redis must be private
- artifact storage must not be world-readable
- management endpoints must be protected

## Encryption

- TLS for ingress traffic in production
- TLS for provider calls where supported by the provider
- encryption at rest for managed Postgres and object storage where supported

## Operator Actions That Must Be Audited

- model registration
- routing-policy changes
- approval and rejection of training candidates where manually controlled
- deployment promotion
- rollback execution
- secret-backend changes

## Access Tiers

- `operator`
- `deployer`
- `viewer`
- `automation`

The first implementation may use simpler auth, but role boundaries must remain conceptually separable.

## Security Review Gate

A deployment is not production-ready unless:

- secrets are externalized
- TLS is configured
- database and Redis are private
- privileged actions are auditable
- identity assignment follows least privilege
