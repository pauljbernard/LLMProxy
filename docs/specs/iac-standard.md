# Infrastructure as Code Standard

## Purpose

This document defines the canonical infrastructure-as-code approach for `llmProxy` so different agents produce near-identical infrastructure outputs.

## Primary IaC Tooling

The project must use:

- `OpenTofu` as the canonical infrastructure provisioning tool
- `Terraform-compatible HCL` module structure
- `Kubernetes YAML` as the canonical deployment manifest format

Terraform may be tolerated where OpenTofu execution is unavailable, but the source layout and syntax must remain OpenTofu-compatible.

## Repository Layout

Infrastructure code must use this top-level layout:

```text
infra/
  tofu/
    modules/
      network/
      postgres/
      redis/
      storage/
      secrets/
      kubernetes_cluster/
      observability/
      llmproxy_app/
    environments/
      local/
      aws/
      gcp/
      azure/
  kubernetes/
    base/
    overlays/
      local/
      aws/
      gcp/
      azure/
  compose/
    docker-compose.yml
    .env.example
```

Agents must not invent alternate top-level infrastructure directories.

## Environment Model

Each target environment must have:

- one environment entrypoint under `infra/tofu/environments/<env>/`
- one Kubernetes overlay under `infra/kubernetes/overlays/<env>/`
- one environment-specific variables file

Supported environments:

- `local`
- `aws`
- `gcp`
- `azure`

## Module Boundaries

Each OpenTofu module must have a single primary responsibility:

- `network/`
- `postgres/`
- `redis/`
- `storage/`
- `secrets/`
- `kubernetes_cluster/`
- `observability/`
- `llmproxy_app/`

Agents must not create giant all-in-one infrastructure modules.

## State Standard

- Use remote state for cloud environments.
- Use local state only for `local`.
- State locking is required where supported.
- Cloud backends must be private and encrypted.

## Variable Naming Standard

Use `snake_case` variable names.

Required common variables:

- `environment_name`
- `project_name`
- `region`
- `vpc_cidr`
- `db_instance_class`
- `redis_instance_class`
- `artifact_bucket_name`
- `container_image`
- `container_image_tag`
- `replica_count_api`
- `replica_count_worker`
- `enable_local_model_runtime`

## Output Standard

Each environment entrypoint must output at minimum:

- `api_endpoint`
- `database_endpoint`
- `redis_endpoint`
- `artifact_storage_name`
- `secret_backend_name`
- `kubernetes_namespace`

## Provisioning Scope

IaC must provision:

- networking
- application runtime substrate
- managed Postgres
- managed Redis
- artifact storage
- secret backend bindings
- ingress
- observability bindings

IaC should not provision remote frontier model providers.

## Drift Rule

Agents must not hand-edit cloud resources outside IaC as part of the standard implementation flow.

## Portability Rule

The same logical modules must exist for all cloud environments even if the provider-specific resource types differ.
