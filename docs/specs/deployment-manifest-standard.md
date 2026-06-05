# Deployment Manifest Standard

## Purpose

This document defines the canonical manifest format and structure for local and Kubernetes deployments.

## Canonical Deployment Targets

The project must maintain:

- Docker Compose manifests for `local`
- Kubernetes base manifests
- Kubernetes overlays for `aws`, `gcp`, and `azure`

## Kubernetes Layout

Use:

```text
infra/kubernetes/base/
  namespace.yaml
  configmap.yaml
  api-deployment.yaml
  api-service.yaml
  worker-deployment.yaml
  scheduler-deployment.yaml
  ingress.yaml
  hpa-api.yaml
  hpa-worker.yaml
  network-policy.yaml
  pdb-api.yaml
  pdb-worker.yaml
  serviceaccount.yaml
```

Use overlays:

```text
infra/kubernetes/overlays/local/
infra/kubernetes/overlays/aws/
infra/kubernetes/overlays/gcp/
infra/kubernetes/overlays/azure/
```

## Required Kubernetes Workloads

- `llmproxy-api`
- `llmproxy-worker`
- `llmproxy-scheduler`

Optional:

- `llmproxy-model-runtime`

## Namespace Standard

Use namespace:

- `llmproxy`

Per-environment suffixes may be added only when required by platform policy.

## Labels

All Kubernetes resources must include:

- `app.kubernetes.io/name: llmproxy`
- `app.kubernetes.io/component`
- `app.kubernetes.io/part-of: llmproxy`
- `app.kubernetes.io/environment`

## Required Container Settings

All runtime manifests must define:

- image
- image pull policy
- container ports
- environment variables
- secret references
- readiness probe
- liveness probe
- resource requests
- resource limits

## Resource Naming

Use canonical names:

- `llmproxy-api`
- `llmproxy-worker`
- `llmproxy-scheduler`
- `llmproxy-config`
- `llmproxy-secrets`
- `llmproxy-ingress`

## Ingress Standard

Ingress must:

- expose the API service
- terminate TLS in cloud production
- support path routing for health and API endpoints

## Compose Standard

The local Compose manifest must define services:

- `api`
- `worker`
- `scheduler`
- `postgres`
- `redis`
- optional `ollama`

The Compose file must use named volumes for:

- postgres data
- redis data if persisted
- exports
- datasets
- models
- checkpoints
- reports

## Manifest Mutation Rule

The base manifests define the logical application.

Overlays may change:

- image registry
- replica counts
- storage class
- ingress annotations
- cloud identity annotations

Overlays may not change:

- workload names
- port semantics
- core environment variable names
- route structure
