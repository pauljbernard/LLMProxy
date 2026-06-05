# Cloud OpenTofu Mapping

## Purpose

This document defines the canonical provider-specific mapping for the OpenTofu modules.

## AWS

### Module Mappings

- `network`: VPC, subnets, route tables, security groups
- `postgres`: RDS PostgreSQL
- `redis`: ElastiCache Redis
- `storage`: S3 bucket
- `secrets`: Secrets Manager or SSM
- `kubernetes_cluster`: EKS or ECS-supporting substrate if Kubernetes path is selected
- `observability`: CloudWatch integrations
- `llmproxy_app`: namespace bindings, identity bindings, ingress bindings

## GCP

### Module Mappings

- `network`: VPC, subnets, firewall rules
- `postgres`: Cloud SQL PostgreSQL
- `redis`: Memorystore Redis
- `storage`: GCS bucket
- `secrets`: Secret Manager
- `kubernetes_cluster`: GKE or Cloud Run-supporting substrate if selected
- `observability`: Cloud Monitoring and Logging integrations
- `llmproxy_app`: namespace bindings, identity bindings, ingress bindings

## Azure

### Module Mappings

- `network`: VNet, subnets, NSGs
- `postgres`: Azure Database for PostgreSQL
- `redis`: Azure Cache for Redis
- `storage`: Blob Storage account/container
- `secrets`: Key Vault
- `kubernetes_cluster`: AKS or Container Apps-supporting substrate if selected
- `observability`: Azure Monitor and Log Analytics integrations
- `llmproxy_app`: namespace bindings, identity bindings, ingress bindings

## Local

### Module Mappings

- `network`: local Docker network assumptions
- `postgres`: containerized Postgres
- `redis`: containerized Redis
- `storage`: local volumes
- `secrets`: `.env` or local secret injection
- `kubernetes_cluster`: optional local cluster
- `observability`: optional local stack
- `llmproxy_app`: Compose or local K8s bindings
