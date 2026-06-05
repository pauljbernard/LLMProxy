# Operator Playbooks

## Purpose

This document defines the common operator tasks that should be easy to execute.

## Core Playbooks

### First Startup

- provision runtime dependencies
- configure environment variables or secrets
- start API, worker, scheduler, Postgres, and Redis
- validate `/health`
- run smoke chat request

### Add Frontier Provider

- inject provider credentials
- verify provider capability metadata
- run provider smoke test
- confirm routing eligibility

### Approve and Export Candidates

- review eligible candidates
- approve or reject
- export JSONL and manifest
- validate artifact outputs

### Run Evaluation

- load benchmark set
- execute evaluation run
- inspect scores and economics report

### Promote Model

- verify promotion thresholds
- verify frontier comparison
- verify deployment target readiness
- register and promote model

### Rollback

- identify prior production model
- restore prior routing target
- confirm health
- log rollback reason

## Rule

If a common operator task requires undocumented steps, the artifact set is incomplete.
