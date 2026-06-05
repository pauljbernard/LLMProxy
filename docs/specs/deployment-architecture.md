# Deployment Architecture

## Purpose

This document defines the canonical production deployment topologies for:

- local single-operator deployment
- AWS deployment
- GCP deployment
- Azure deployment

The goal is to keep the application architecture constant while allowing environment-specific infrastructure substitutions.

## Logical Components

Every deployment must contain these logical components:

1. API service
2. background worker service
3. Postgres database
4. Redis cache and task broker
5. object or artifact storage
6. local-model runtime where applicable
7. observability stack
8. secret-management mechanism
9. ingress and TLS termination layer

## Canonical Runtime Split

The production runtime should be deployed as at least these process groups:

- `api`
- `worker`
- `scheduler`
- `postgres`
- `redis`
- `model_runtime` where local inference is enabled

The `api`, `worker`, and `scheduler` roles may share the same image, but must run as separate processes or deployments.

## Local Reference Topology

Local production-like deployment should use:

- Docker Compose
- local Postgres
- local Redis
- optional Ollama, vLLM, llama.cpp, or MLX runtime
- local persistent volumes for models, exports, checkpoints, and reports
- reverse proxy with TLS optional for single-user operation

Local mode is the canonical developer and single-operator environment.

## AWS Reference Topology

AWS deployment should map to:

- `api`: ECS Fargate or EKS deployment
- `worker`: ECS Fargate or EKS deployment
- `scheduler`: ECS scheduled task or EKS CronJob
- `postgres`: Amazon RDS for PostgreSQL
- `redis`: Amazon ElastiCache for Redis
- `artifacts`: S3
- `secrets`: AWS Secrets Manager or SSM Parameter Store
- `ingress`: ALB or API Gateway plus ALB
- `observability`: CloudWatch plus OpenTelemetry-compatible export
- `identity`: IAM roles for tasks or service accounts

If Bedrock is used, it is a remote provider dependency and not a substitute for the proxy’s own runtime services.

## GCP Reference Topology

GCP deployment should map to:

- `api`: GKE deployment or Cloud Run service
- `worker`: GKE deployment or Cloud Run job where compatible
- `scheduler`: Cloud Scheduler plus Cloud Run job or GKE CronJob
- `postgres`: Cloud SQL for PostgreSQL
- `redis`: Memorystore for Redis
- `artifacts`: Google Cloud Storage
- `secrets`: Secret Manager
- `ingress`: Cloud Load Balancing
- `observability`: Cloud Logging, Cloud Monitoring, and OpenTelemetry-compatible export
- `identity`: Workload Identity

GCP is a required deployment target even though it is not a required frontier-provider family.

## Azure Reference Topology

Azure deployment should map to:

- `api`: AKS deployment or Azure Container Apps where compatible
- `worker`: AKS deployment or Container Apps job
- `scheduler`: AKS CronJob or scheduled Container Apps job
- `postgres`: Azure Database for PostgreSQL
- `redis`: Azure Cache for Redis
- `artifacts`: Azure Blob Storage
- `secrets`: Azure Key Vault
- `ingress`: Application Gateway, Front Door, or AKS ingress controller
- `observability`: Azure Monitor, Log Analytics, and OpenTelemetry-compatible export
- `identity`: Managed Identity

Azure OpenAI remains a provider target and does not replace the proxy control plane.

## Network Zones

Production deployments should separate:

- public ingress layer
- private application services
- private data services
- optional isolated GPU or model-runtime nodes

The database, Redis, and artifact stores must not be directly exposed to the public internet.

## Scaling Model

- `api` must scale horizontally.
- `worker` must scale independently from `api`.
- `scheduler` should remain singleton or logically singleton.
- `model_runtime` may scale independently based on domain demand and GPU availability.

## Production Deployment Modes

The system must support:

- single-instance local mode
- small production mode
- highly available production mode

Highly available mode requires:

- at least two `api` replicas
- at least two `worker` replicas for non-exclusive queues
- managed Postgres with backups
- managed Redis or equivalent durable operational setup
- load-balanced ingress

## Release Units

The deployable units are:

- application container image
- Alembic migration set
- environment configuration bundle
- routing-policy configuration
- optional model-runtime deployment bundle

## Non-Portable Assumptions To Avoid

Implementation agents must not assume:

- a local filesystem is always shared across services
- direct shell access to production containers
- a single-node database
- Docker Compose semantics in cloud production
- provider credentials are injected as plain files
