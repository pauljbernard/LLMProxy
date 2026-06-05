# Container and Release Standard

## Purpose

This document defines the canonical build, packaging, release, and rollback process so that deployments are reproducible across environments.

## Container Standard

The project must build at least one primary application image containing:

- API runtime
- worker runtime
- scheduler runtime
- Alembic migrations
- all required Python dependencies

The image entrypoint may vary by role, but the filesystem contents must remain consistent.

## Image Naming

Canonical image name format:

`llmproxy:<git-sha>`

Optional additional tags:

- `llmproxy:<semver>`
- `llmproxy:latest` for non-production convenience only

Production rollouts must reference immutable tags.

## Build Requirements

- lock dependencies
- run tests before publishing release images
- run static checks before publishing release images
- embed version metadata in the image
- expose build commit SHA and version in runtime metadata

## Required Release Artifacts

Each release must include:

- application image tag
- migration version set
- release notes or change summary
- configuration template for the environment
- rollback target version

## Release Pipeline Stages

1. dependency resolution
2. lint and static validation
3. unit and integration tests
4. image build
5. image vulnerability scan
6. publish immutable image
7. run migrations
8. deploy application services
9. verify health checks
10. verify metrics and route sanity

## Migration Order

Production rollout order must be:

1. publish image
2. run Alembic migrations
3. deploy `api`
4. deploy `worker`
5. deploy `scheduler`
6. verify readiness

If migrations are not backward compatible, the release must be blocked unless explicitly approved through a controlled maintenance procedure.

## Rollback Standard

Rollback must support:

- image rollback
- routing-policy rollback
- model-registration rollback

Database rollback should prefer forward-fix unless a reversible migration was explicitly designed and tested.

## Deployment Verification

Every release must verify:

- health endpoint response
- database connectivity
- Redis connectivity
- provider registry load
- basic chat-completion smoke test
- logging and metrics emission

## Multi-Environment Compatibility

The same container image should be deployable in:

- local Docker Compose
- AWS ECS or EKS
- GCP Cloud Run or GKE
- Azure Container Apps or AKS

Environment differences must be handled through configuration, not through separate application forks.
