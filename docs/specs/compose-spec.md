# Docker Compose Specification

## Purpose

This document defines the canonical local deployment manifest behavior.

## Canonical File Path

- `infra/compose/docker-compose.yml`

## Required Services

- `api`
- `worker`
- `scheduler`
- `postgres`
- `redis`

Optional:

- `ollama`

## Required Networks

- one internal application network

## Required Volumes

- `postgres_data`
- `redis_data`
- `exports_data`
- `datasets_data`
- `models_data`
- `checkpoints_data`
- `reports_data`

## Service Behavior

### api

- exposes port `8000`
- depends on `postgres` and `redis`
- mounts configured artifact paths

### worker

- shares the same image as `api`
- uses worker command override
- depends on `postgres` and `redis`

### scheduler

- shares the same image as `api`
- uses scheduler command override
- depends on `postgres` and `redis`

### postgres

- exposes port `5432` optionally for local operator use
- uses persistent named volume

### redis

- exposes port `6379` optionally for local operator use
- uses persistent named volume

### ollama

- optional local model runtime
- separate volume for downloaded models when used

## Environment Contract

Compose must use:

- `.env.example`
- environment variable names from `runtime-environment-spec.md`

## Local Production-Like Rule

The Compose environment must be suitable for:

- local development
- local single-operator production-like testing
- smoke testing release artifacts before cloud deployment
