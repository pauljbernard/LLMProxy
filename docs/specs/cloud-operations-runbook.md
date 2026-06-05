# Cloud Operations Runbook

## Purpose

This runbook defines the minimum operational expectations for running the proxy in production-like environments.

## Operational Domains

Operations must cover:

- availability
- latency
- cost
- data integrity
- provider health
- security events
- training and deployment safety

## Observability Stack

Every production deployment must provide:

- centralized logs
- metrics collection
- distributed tracing or equivalent request-correlation mechanism
- dashboarding
- alerting

## Minimum Dashboards

- API traffic and latency
- provider health and failure rates
- route mix and fallback rates
- cost by provider and domain
- worker queue depth and job latency
- training and evaluation status
- deployment and rollback activity

## Minimum Alerts

- API error rate exceeds threshold
- p95 latency exceeds threshold
- provider fallback rate spikes
- database unavailable
- Redis unavailable
- queue backlog exceeds threshold
- deployment health check fails
- rollback triggered
- avoided frontier spend collapses unexpectedly for a promoted specialist

## Suggested Initial SLOs

- API availability: `99.5%`
- successful request completion: `99.0%`
- p95 latency for non-ensemble requests: environment-specific, must be declared
- critical rollback execution: `100%` when triggered

## Backup and Recovery

Production operations must include:

- daily Postgres backups at minimum
- point-in-time recovery where supported
- artifact-store durability policy
- periodic restore test
- documented RPO and RTO targets

## Log Retention

At minimum retain:

- operational logs: `30` days
- security logs: `90` days
- audit and routing decision records: according to operator policy, default `90` days minimum

## Incident Classes

- `SEV1`: full outage or unsafe production behavior
- `SEV2`: major degradation, widespread fallback, or deployment failure
- `SEV3`: partial feature impairment
- `SEV4`: non-urgent defect or noise issue

## First Response Actions

### API Outage

1. confirm ingress health
2. confirm application readiness
3. confirm database and Redis connectivity
4. inspect recent rollout state
5. rollback if release-induced

### Provider Degradation

1. confirm provider-family impact
2. confirm fallback-chain success
3. reduce routing eligibility for degraded provider
4. notify operators if degradation persists

### Database Incident

1. freeze risky write-heavy maintenance jobs if needed
2. assess primary availability
3. fail over according to platform capability
4. restore from backup only if failover is not sufficient

## Cost Operations

Operators must review:

- daily blended cost
- daily frontier spend
- per-domain local substitution rate
- promoted specialist ROI

Unexpected cost increases must trigger routing-policy review.
