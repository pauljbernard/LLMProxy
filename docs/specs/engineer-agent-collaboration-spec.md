# Engineer-Agent Collaboration Specification

## Purpose

This document defines how a human engineer and a coding agent should collaborate efficiently during implementation.

## Human Engineer Responsibilities

- set priorities
- answer clarifying questions when required
- approve scope changes
- review major contract, security, and production-impact changes

## Coding Agent Responsibilities

- follow the spec pack
- work iteratively
- surface assumptions early
- report bounded progress clearly
- avoid silent scope expansion
- request clarification only when necessary

## Interaction Rules

- the agent should prefer progress over repeated planning
- the engineer should prefer concrete answers over open-ended guidance
- iteration reports should make it obvious whether the agent can continue autonomously

## Escalation Cases

The agent should escalate when:

- a normative conflict exists between artifacts
- a security or governance decision is unclear
- a contract-breaking change may be required
- an implementation path would violate the checklist or review gates

## Efficiency Rule

The engineer should not need to reconstruct the agent’s state from raw diffs alone. The agent’s progress reports must explain the current position and next action.
