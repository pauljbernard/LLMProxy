# Infrastructure Mapping

## Purpose

This document maps the logical system components to concrete local, AWS, GCP, and Azure infrastructure choices.

## Logical To Physical Mapping

| Logical Component | Local | AWS | GCP | Azure |
|---|---|---|---|---|
| API service | Docker Compose service | ECS Fargate or EKS | Cloud Run or GKE | Container Apps or AKS |
| Worker service | Docker Compose service | ECS Fargate or EKS | Cloud Run job or GKE | Container Apps job or AKS |
| Scheduler | Compose service or cron | ECS scheduled task or EKS CronJob | Cloud Scheduler plus job or GKE CronJob | scheduled Container Apps job or AKS CronJob |
| Postgres | local container | RDS PostgreSQL | Cloud SQL PostgreSQL | Azure Database for PostgreSQL |
| Redis | local container | ElastiCache Redis | Memorystore Redis | Azure Cache for Redis |
| Artifact storage | local volume | S3 | GCS | Blob Storage |
| Secrets backend | env or local store | Secrets Manager or SSM | Secret Manager | Key Vault |
| Ingress | reverse proxy | ALB | Cloud Load Balancer | Application Gateway or Front Door |
| Observability | local stack | CloudWatch plus OTEL | Cloud Monitoring plus OTEL | Azure Monitor plus OTEL |
| Identity | local env | IAM role | Workload Identity | Managed Identity |

## Local Inference Mapping

| Local Model Runtime | Local | AWS | GCP | Azure |
|---|---|---|---|---|
| Ollama | native or container | EC2/EKS GPU node if needed | GCE/GKE GPU node if needed | VM/AKS GPU node if needed |
| vLLM | local GPU host | EKS/ECS on GPU-backed compute | GKE/GCE on GPU-backed compute | AKS/VM on GPU-backed compute |
| llama.cpp | local CPU/GPU host | EC2 or EKS | GCE or GKE | VM or AKS |
| MLX | Apple Silicon local only | not primary | not primary | not primary |

## Environment Profiles

### Local

Use for:

- single-user operation
- development
- benchmark iteration
- training on local hardware where feasible

### AWS

Use for:

- managed production services
- Bedrock adjacency
- private VPC deployment
- scalable worker execution

### GCP

Use for:

- managed production services
- Cloud Run or GKE operation
- private service networking
- strong managed Postgres and secret tooling

### Azure

Use for:

- managed production services
- Azure OpenAI adjacency
- AKS or Container Apps
- enterprise identity integration

## Canonical Portability Rule

The proxy application code must remain the same across all environments. Only infrastructure bindings, secrets, and configuration values change.
