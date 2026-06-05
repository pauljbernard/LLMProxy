# Performance SLO Specification

## Purpose

This document defines initial quantitative performance expectations for the first production-capable version.

## Route Classes

- `local_single`
- `frontier_single`
- `frontier_ensemble`
- `dataset_job`
- `training_job`

## Initial Request Latency Targets

### API Availability

- availability target: `99.5%`

### Non-Streaming Chat Requests

- `local_single` p95 latency: `<= 8s`
- `frontier_single` p95 latency: `<= 15s`
- `frontier_ensemble` p95 latency: `<= 35s`

### Health Endpoints

- `/health` p95 latency: `<= 500ms`

## Error Targets

- non-ensemble request error rate: `< 1%`
- fallback invocation rate spike threshold: `> 10%` over rolling baseline triggers investigation

## Queue Targets

- dataset import queue backlog: investigate if oldest pending job exceeds `10m`
- evaluation queue backlog: investigate if oldest pending job exceeds `15m`
- deployment queue backlog: investigate if oldest pending job exceeds `5m`

## Release Verification Targets

- smoke test chat request must succeed within `20s`
- deployment verification must complete within `10m`

## Precision Rule

These targets are initial guardrails. Production tuning may adjust them, but changes require explicit versioned documentation updates.
