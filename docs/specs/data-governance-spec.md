# Data Governance Specification

## Purpose

This document defines the data retention, privacy, handling, and governance expectations for `llmProxy`.

## Data Classes

The system must distinguish at minimum:

- request and response logs
- routing decision records
- training candidates
- exported datasets
- benchmark assets
- provider credentials and secrets
- evaluation reports

## Privacy Levels

Supported privacy levels:

- `public`
- `normal`
- `private`
- `restricted`

Privacy level must influence:

- routing eligibility
- storage handling
- export eligibility
- retention policy

## Retention Principles

- retain only what is operationally or analytically justified
- avoid retaining secret-bearing or blocked records
- preserve audit-critical records according to operator policy

## Default Retention Guidance

- operational request logs: `30-90` days
- routing decision logs: `90` days minimum
- approved training candidates: operator-defined, default `90` days minimum
- rejected or blocked records: retain only as needed for audit, default shorter retention
- exported datasets and manifests: retain according to training reproducibility policy
- evaluation and promotion records: retain for reproducibility and rollback history

## Export Governance

Records may not be exported if they:

- contain secrets
- are blocked
- are rejected
- violate privacy policy
- exceed allowed governance restrictions for their privacy level

## Provider Data Handling

When remote frontier providers are used:

- routing policy must respect privacy mode
- provider usage must be auditable
- restricted data must not be sent remotely when policy forbids it

## Deletion and Purge Expectations

The system should support:

- deleting expired operational logs
- purging quarantined invalid records when safe
- retracting exports that should not have been produced
- retaining immutable audit markers when full deletion is not appropriate

## Compliance Posture

The first implementation is not required to claim formal regulatory certification, but it must be structured so operators can:

- understand data movement
- apply retention rules
- audit export eligibility
- enforce local-only privacy mode

## Governance Review Triggers

Changes require governance review when they affect:

- exported fields
- retention durations
- privacy classification logic
- provider-routing rules for restricted data
