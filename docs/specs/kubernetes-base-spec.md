# Kubernetes Base Specification

## Purpose

This document defines the canonical Kubernetes behavior expected from the base manifests.

## Base Workload Definitions

### API Deployment

Must include:

- deployment named `llmproxy-api`
- port `8000`
- readiness probe on `/health`
- liveness probe on `/health`
- configurable replica count
- rolling update strategy

### Worker Deployment

Must include:

- deployment named `llmproxy-worker`
- no public service exposure
- queue connectivity checks
- configurable replica count

### Scheduler Deployment

Must include:

- deployment named `llmproxy-scheduler` or a singleton job-like controller
- exactly one replica by default

## Services

- `llmproxy-api` must be exposed as a ClusterIP service
- worker and scheduler do not require public services

## Autoscaling

Must define HPA for:

- `llmproxy-api`
- `llmproxy-worker`

Scheduler should not autoscale by default.

## Availability Controls

Must include:

- PodDisruptionBudget for `api`
- PodDisruptionBudget for `worker`
- anti-affinity for `api` in highly available environments where possible

## Security Controls

Must include:

- non-root containers where feasible
- read-only root filesystem where feasible
- dropped Linux capabilities where feasible
- secret references instead of inline secret values

## Config Injection

Use:

- ConfigMap for non-secret configuration
- Secret references for sensitive configuration

## Optional Model Runtime

If `llmproxy-model-runtime` is deployed in Kubernetes, it must:

- remain logically separate from `api`
- support its own resource sizing
- optionally target GPU nodes
