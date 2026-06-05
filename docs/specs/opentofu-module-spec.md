# OpenTofu Module Specification

## Purpose

This document defines the canonical structure and expectations for OpenTofu modules.

## Module File Layout

Each module under `infra/tofu/modules/<module>/` must contain:

```text
main.tf
variables.tf
outputs.tf
versions.tf
README.md
```

Optional:

- `locals.tf`
- `data.tf`

## Environment Entrypoint Layout

Each environment under `infra/tofu/environments/<env>/` must contain:

```text
main.tf
variables.tf
outputs.tf
versions.tf
terraform.tfvars.example
README.md
```

## Provider Standard

Each cloud environment must declare only the provider(s) necessary for that environment:

- AWS environment: AWS provider
- GCP environment: Google provider
- Azure environment: AzureRM provider

Local environment may use no cloud provider and only local provisioning logic where necessary.

## Module Interface Rules

Modules must:

- expose explicit inputs and outputs
- avoid hidden cross-module dependencies
- avoid hard-coded environment names
- accept tags or labels where relevant

## Naming Convention

Module names must match the names in `iac-standard.md`.

Resource names should be derived from:

- `project_name`
- `environment_name`

## Environment Composition

Each environment entrypoint must compose modules in this order:

1. `network`
2. `secrets`
3. `storage`
4. `postgres`
5. `redis`
6. `kubernetes_cluster`
7. `observability`
8. `llmproxy_app`

## Output Rule

Environment outputs must be sufficient for deployment verification and operator handoff.

## Prohibited Variance

Agents must not:

- inline all resources into an environment file
- skip module READMEs
- create environment-specific resource naming schemes that break portability
