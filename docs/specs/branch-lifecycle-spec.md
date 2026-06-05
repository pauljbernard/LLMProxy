# Branch Lifecycle Specification

## Purpose

This document defines how branches should be created, used, merged, and retired during multi-day implementation work.

## Default Branch Types

- `main`
- `codex/<topic>`
- `feature/<topic>`
- `fix/<topic>`
- `release/<version>`

## Default Rule For Coding Agents

Coding agents should default to a `codex/<topic>` branch for active implementation work unless a human engineer specifies another branch strategy.

## Branch Creation Rule

Create a new branch when:

- starting a new phase or major sub-phase
- work would otherwise mix unrelated concerns
- a risky change needs isolated review

Continue an existing branch when:

- the active work remains inside the same bounded scope
- the branch has not drifted into unrelated tasks

## Merge Rule

A branch should be merged only when:

- acceptance criteria for the bounded scope are satisfied
- review gates are satisfied
- required tests and validations are complete
- documentation and decision logs are updated where needed

## Branch Hygiene

Branches must avoid:

- carrying unrelated changes
- mixing docs-only work with major code changes unless tightly coupled
- remaining open after the bounded scope is complete without explicit reason

## Release Branch Rule

Use `release/<version>` only when preparing a coordinated release candidate that may require:

- migration review
- deployment artifact review
- release verification

## Retirement Rule

After merge or abandonment:

- branch purpose should be considered closed
- follow-up work should start on a new branch unless it is still the same bounded scope
