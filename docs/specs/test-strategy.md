# Test Strategy

## Purpose

This document defines the canonical testing strategy across the application, infrastructure, and operations layers.

## Test Pyramid

The project should use this testing distribution:

1. unit tests
2. integration tests
3. end-to-end tests
4. performance and resilience tests
5. security and compliance checks

## Required Test Categories

### Unit Tests

Cover:

- classifiers
- routing-policy scoring
- provider adapters
- dataset validation and normalization
- KPI and economics calculations
- schema validation

### Integration Tests

Cover:

- API to database persistence
- API to Redis queue interactions
- provider adapter normalization
- export and import flows
- training orchestration contracts
- deployment registration flows

### End-to-End Tests

Cover:

- `POST /v1/chat/completions` local route
- `POST /v1/chat/completions` frontier route
- `POST /proxy/ensemble`
- candidate approval to export flow
- dataset import to version creation flow
- training run submission to evaluation flow
- model registration and rollback flow

### Performance Tests

Cover:

- steady-state API latency
- provider fallback under degradation
- queue backlog handling
- route-mix cost calculations under load

### Security Tests

Cover:

- secret redaction
- auth enforcement
- ingress exposure checks
- private service accessibility assumptions
- unsafe export prevention

## Ownership

- `app/tests/api/`: API tests
- `app/tests/proxy/`: routing, ensemble, judge, recorder tests
- `app/tests/providers/`: adapter normalization and provider error-path tests
- `app/tests/datasets/`: validation, dedupe, split tests
- `app/tests/training/`: orchestration and config tests
- `app/tests/evaluation/`: benchmark, scoring, economics tests
- `app/tests/deployment/`: registry and rollback tests
- `app/tests/integration/`: workflow and contract tests
- `infra/`: infrastructure validation and manifest checks

## Minimum Merge Gates

Every non-doc change must pass:

- unit tests for touched modules
- integration tests for touched contracts
- schema validation
- lint and static checks

Changes affecting routing, exports, schemas, or infra must also pass:

- targeted end-to-end tests

## Minimum Release Gates

Release candidates must pass:

- full unit suite
- full integration suite
- smoke end-to-end tests
- migration validation
- deployment artifact validation
- security checks

## Test Data Rules

- test fixtures must avoid real secrets
- benchmark holdout sets must not be polluted by training data
- counterfactual cost tests must use deterministic fixtures

## Coverage Rule

Code coverage percentage alone is not sufficient. Critical paths must have behavior coverage even if aggregate coverage is high.

Critical paths include:

- routing decision persistence
- fallback selection
- candidate export gating
- import validation
- promotion gate logic
- rollback execution
