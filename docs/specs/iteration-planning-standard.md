# Iteration Planning Standard

## Purpose

This document defines how implementation work should be broken into manageable steps.

## Planning Unit

The preferred planning unit is:

- one phase
- split into sub-phases
- split into bounded implementation iterations

## Good Iteration Characteristics

A good iteration should:

- produce a visible outcome
- touch a coherent part of the system
- be testable
- fit naturally into the current phase

## Bad Iteration Characteristics

Avoid iterations that:

- span unrelated subsystems
- add code without tests or validation
- change contracts and implementation without updating artifacts
- leave critical paths half-migrated without explanation

## Recommended Iteration Types

- contract-first iteration
- persistence iteration
- provider-adapter iteration
- API-slice iteration
- infra wiring iteration
- validation and test iteration

## Phase Progress Rule

Progress should be reported against the current phase and subtask, not as an arbitrary subjective estimate.
