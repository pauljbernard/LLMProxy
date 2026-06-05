# Implementation Charter

## Purpose

This charter exists to reduce unnecessary creativity during implementation. The goal is consistent execution, not architectural reinterpretation.

## Core Rule

Implement the documented system. Do not redesign it unless the spec pack is explicitly changed first.

## Required Agent Behavior

Implementation agents must:

- follow the module and directory layout in `repository-standard.md`
- implement contracts before adding convenience abstractions
- prefer direct, readable code over framework-heavy indirection
- preserve explicit boundaries between proxy, learner, evaluation, deployment, and integration concerns
- implement the simplest solution that satisfies the spec and tests

## Do Not Improvise

Implementation agents must not improvise in these areas:

- replacing named providers with different initial provider priorities
- inventing alternate routing-policy concepts
- changing canonical KPI definitions
- replacing designated contract fields with similar but incompatible names
- introducing event types not described in the spec pack without documenting them
- using different database schemas or table namespaces
- changing the benchmark or promotion model without updating the specs

## Default Decision Rule

If multiple implementations could satisfy a requirement, choose the option that:

1. matches the named file/module destination in the spec pack
2. preserves explicit data contracts
3. minimizes hidden behavior
4. minimizes dependency count
5. is easiest for another agent to continue

## Escalation Rule

If a requirement is ambiguous, the agent should:

1. check `glossary.md`
2. check `repository-standard.md`
3. check `metrics-spec.md`
4. check `data-contracts.md`
5. use the most conservative interpretation

The agent should not silently invent a new architecture because the first-pass docs leave room for taste.

## Completion Rule

A task is not complete merely because code compiles. It is complete when:

- code matches the declared module boundaries
- contracts are implemented consistently
- telemetry fields needed by KPIs are persisted
- tests cover the expected behavior
- the implementation remains aligned with the spec pack
