# Clarification and Decision Log Specification

## Purpose

This document defines how unresolved questions and human decisions should be captured during iterative implementation.

## Rule

If a coding agent must stop for clarification, the question and resulting decision should be recorded in a durable log artifact.

## Canonical Log Path

- `docs/decision-log.md`

## Required Log Fields

- date
- active phase
- question
- reason clarification was needed
- decision
- impact on implementation

## When Logging Is Required

- contract interpretation changes
- architecture exceptions
- security-sensitive decisions
- routing-policy threshold overrides
- changes to adoption profile assumptions

## Benefit

This prevents the same unresolved issue from being rediscovered by later agents.
