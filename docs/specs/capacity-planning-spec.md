# Capacity Planning Specification

## Purpose

This document defines initial capacity assumptions and scaling triggers.

## Baseline Roles

- `api`
- `worker`
- `scheduler`
- optional `model_runtime`

## Initial Scaling Assumptions

- `api` should scale horizontally from `2` replicas in HA environments
- `worker` should scale independently from `api`
- `scheduler` should run as `1` replica by default

## Trigger Thresholds

- API CPU sustained above `70%` should justify scale-out
- worker queue growth for `10m` with no recovery should justify scale-out
- repeated provider fallbacks due to timeouts should trigger route/capacity review

## Database Capacity Review Triggers

Review database sizing when:

- request log growth exceeds retention assumptions
- p95 DB query latency threatens request SLOs
- export/import workloads materially impact API responsiveness

## Model Runtime Review Triggers

Review local model runtime placement when:

- local specialist traffic exceeds current hardware throughput
- GPU-bound evaluation/training workloads interfere with serving
- route mix shifts materially toward local inference

## Planning Rule

Capacity planning is not complete at design time alone. Operators must review telemetry and revise sizing with real usage data.
