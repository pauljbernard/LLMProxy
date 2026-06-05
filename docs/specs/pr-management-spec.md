# Pull Request Management Specification

## Purpose

This document defines how pull requests should be structured for manageable review during iterative implementation.

## PR Scope Rule

A pull request should represent:

- one bounded implementation slice
- one coherent set of code, tests, and artifact updates

Avoid PRs that:

- mix unrelated subsystems
- combine large refactors with new behavior
- defer critical test coverage to later PRs without explicit approval

## Draft PR Rule

Use draft PRs when:

- a multi-day branch needs early visibility
- architecture or contract review is needed before final completion
- work is intentionally incomplete but worth reviewing

## PR Required Sections

Each PR should include:

- purpose
- scope
- completed work
- remaining work if draft
- validation performed
- deployment impact
- rollback considerations
- clarification or decision-log references where relevant

## PR Size Guidance

Prefer:

- small to medium PRs for code-heavy work
- separate PRs for major infra, contract, or migration changes when practical

## Stacked PR Rule

If one phase produces multiple dependent slices, PRs may be stacked, but each PR must remain reviewable on its own.

## Merge Blocking Conditions

Do not merge if:

- critical-path placeholders remain in claimed complete scope
- contracts changed without artifact update
- migrations changed without migration review
- validation evidence is missing
- decision log is required but not updated
