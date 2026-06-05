# CI/CD Specification

## Purpose

This document defines the canonical continuous integration and continuous delivery workflow.

## CI Pipeline Stages

Every change pipeline must support these stages:

1. dependency setup
2. lint and formatting validation
3. static type or schema validation
4. unit tests
5. integration tests
6. infrastructure validation
7. image build
8. artifact publication for approved branches or tags

## Required CI Checks

- Python dependency install succeeds
- application imports succeed
- schema checks succeed
- tests pass
- OpenTofu formatting and validation succeed
- Kubernetes manifest validation succeeds
- Docker build succeeds

## Release Pipeline Stages

1. build immutable image
2. scan image
3. package migration set
4. validate manifests
5. deploy to target environment
6. run smoke tests
7. verify health and metrics
8. promote or rollback

## Branch Behavior

- feature or codex branches: run CI only
- release branches: run CI plus release-candidate packaging
- version tags: run full release pipeline

## Artifact Rules

CI/CD must publish or retain:

- test reports
- image tag metadata
- migration metadata
- manifest validation output
- deployment verification evidence

## Environment Promotion Model

Preferred flow:

1. local verification
2. non-production cloud environment
3. production

The same application image must move forward through environments.

## Failure Rule

Failed CI or failed release verification blocks promotion.

## Secret Handling Rule

Pipelines must use managed secret injection and must not print secrets in logs.
