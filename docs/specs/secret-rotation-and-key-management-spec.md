# Secret Rotation and Key Management Specification

## Purpose

This document defines the minimum lifecycle expectations for secrets and keys used by `llmProxy`.

## Secret Categories

- provider API keys
- bearer tokens
- database credentials
- Redis credentials
- CI/CD secrets

## Core Rules

- secrets must not be committed to source control
- secrets must be injected through approved backends
- secret use should be minimized to the smallest required scope

## Rotation Expectations

The system and operations model should support:

- rotating provider API keys
- rotating bearer tokens
- rotating database credentials where applicable
- rotating CI/CD secrets

## Cloud Backends

- AWS: Secrets Manager or SSM
- GCP: Secret Manager
- Azure: Key Vault

## Audit Expectations

Changes to secret backend configuration or privileged credentials should be auditable.

## Recovery Rule

If a secret is suspected compromised:

- rotate it
- assess affected systems and routes
- review related audit records
- invalidate dependent sessions or workflows if appropriate
