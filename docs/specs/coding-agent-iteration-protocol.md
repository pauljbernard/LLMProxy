# Coding Agent Iteration Protocol

## Purpose

This document defines how coding agents should execute work over multiple iterations so progress remains visible, controlled, and efficient.

## Core Rule

The system is not expected to be built in one pass.

Implementation agents must work in bounded iterations and report status after each meaningful iteration.

## Required Iteration Report

After each iteration, the agent must report:

- what was completed
- current estimated percent complete for the active plan
- what comes next
- any blockers
- any clarification required before continuing
- any risk, regression, or assumption introduced during the iteration

## Iteration Size

An iteration should usually correspond to one of:

- one small end-to-end slice
- one major subtask inside the current phase
- one coherent set of related code, test, and contract updates

Agents must avoid combining unrelated work into a single opaque iteration.

## Iteration Completion Rule

An iteration is complete only when:

- code changes are made or an explicit no-change decision is justified
- relevant tests or validations are run where possible
- artifacts are updated if behavior or contracts changed
- the iteration report is produced

## Required Status Fields

Each status update should include:

- `Completed`
- `Progress`
- `Next`
- `Needs Clarification` when applicable

## Percent Complete Rule

Percent complete must refer to the active implementation plan or active task scope, not the whole lifetime of the project unless explicitly stated.

## Clarification Rule

The agent should continue autonomously unless:

- a decision would alter a normative contract
- a change would conflict with the spec pack
- a risk is high and not clearly resolvable from artifacts
- a user preference is required

When clarification is needed, the agent should ask the minimum precise question needed to continue.

## Blocker Rule

If blocked, the agent must report:

- the blocker
- what was attempted
- what specific input or decision is needed

## Iteration Hygiene

Agents must avoid:

- vague progress updates
- hiding untested changes
- claiming completion without validation
- silently changing scope
