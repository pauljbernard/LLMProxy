# Engineering Workflow Standard

## Purpose

This document defines the canonical engineering workflow for implementing, reviewing, releasing, and maintaining `llmProxy`.

## Branching Standard

Use these branch categories:

- `main`
- `codex/<topic>`
- `feature/<topic>`
- `fix/<topic>`
- `release/<version>`

`main` is the protected integration branch.

Implementation agents should default to `codex/<topic>` unless a human operator specifies otherwise.

## Commit Standard

Commits should be:

- small enough to review
- scoped to one concern where practical
- descriptive and imperative

Preferred commit style:

- `feat: add openai-compatible chat endpoint`
- `fix: persist routing decision fallback chain`
- `docs: add OpenTofu module standard`

## Pull Request Standard

Every non-trivial change should land through a pull request or equivalent review artifact.

Each PR must include:

- purpose
- scope
- impacted subsystems
- test evidence
- deployment impact
- rollback considerations

## Review Requirements

The following changes require explicit review before merge:

- API contract changes
- database schema changes
- routing-policy changes
- promotion-threshold changes
- security or secret-handling changes
- infrastructure module changes
- CI/CD pipeline changes

## Definition of Ready

A work item is ready for implementation when:

- requirements are identified
- affected artifacts are named
- acceptance criteria are available
- contract impact is understood
- rollout risk is understood

## Definition of Done

A work item is done when:

- implementation matches the spec pack
- tests are added or updated
- documentation is updated where behavior changed
- operational impact is understood
- rollback path is preserved

## Release Approval Standard

A release candidate requires approval when it includes:

- migrations
- contract changes
- routing-policy changes
- infrastructure changes
- new provider adapters
- model-promotion logic changes

## Emergency Change Rule

Emergency fixes may use a shortened workflow, but must still include:

- minimal test evidence
- explicit rollback plan
- post-change documentation catch-up

## Agent Discipline Rule

Implementation agents must not bypass workflow expectations by treating code generation as a substitute for review discipline.
