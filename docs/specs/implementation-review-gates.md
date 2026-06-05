# Implementation Review Gates

## Purpose

These gates define merge blockers for implementation work.

## Merge Blockers

- new modules added outside canonical repo structure without spec update
- endpoint behavior changed without contract update
- schema changed without migration update
- privileged operation added without audit requirement consideration
- secret handling added outside approved secret paths
- critical-path logic left as placeholder implementation
- routing behavior changed without routing-policy review
- infra changes made outside canonical `infra/` structure

## Critical Paths

The following may not remain stubbed on a claimed completed phase:

- auth on privileged endpoints
- request persistence
- routing decision persistence
- export gating
- rollback logic
- provider fallback handling
