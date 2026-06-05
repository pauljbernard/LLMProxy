# Implementation Session Template

## Purpose

This template defines the expected structure for a coding-agent implementation session.

## Session Start

At the beginning of a session, the agent should state:

- active phase
- active subtask
- relevant artifacts being followed
- first concrete action

## Session Flow

Each session should follow this pattern:

1. orient to the active phase and artifacts
2. inspect current repo state
3. implement one bounded iteration
4. validate changes
5. report iteration status
6. either continue to the next bounded iteration or stop if clarification is required

## Session End

At the end of a session, the agent should state:

- what was completed in the session
- percent complete for the active plan
- what remains
- what should happen next
- any unresolved issue or required clarification
