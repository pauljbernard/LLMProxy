# Multi-Session Implementation Specification

## Purpose

This document defines how coding-agent work should resume cleanly across multiple days or sessions.

## Session Resume Rule

At the start of a new session, the agent must:

1. inspect current repo state
2. inspect current branch state
3. review recent iteration reports or session summary
4. review `docs/decision-log.md` for unresolved or recent decisions
5. restate the active phase and next bounded task

## End-of-Session Rule

At the end of a session, the agent must leave enough information so another agent or a later session can continue without reconstructing context from diffs alone.

This includes:

- current progress
- remaining work
- known blockers
- required clarifications
- validation status

## Branch Continuity Rule

If work resumes on the same branch across days:

- the branch purpose must still be coherent
- unrelated work must not be added silently

If the branch has become mixed-scope, the next session should split work into a new branch.

## Checkpointing Rule

Long-running implementation efforts should checkpoint at:

- end of each bounded iteration
- before major refactors
- before pausing unresolved work

## Clarification Carryover Rule

If a clarification was needed in a prior session:

- check whether it was resolved in `docs/decision-log.md`
- do not reopen the same question unless new evidence or scope change requires it

## Session Efficiency Rule

The goal of a new session is not to rediscover state. The artifacts and progress reports should make resumption fast and reliable.
