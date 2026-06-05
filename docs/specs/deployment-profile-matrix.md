# Deployment Profile Matrix

## Purpose

This document defines staged operating profiles so the system can be run with different levels of complexity.

## Profiles

### Minimal

Includes:

- OpenAI-compatible proxy
- one local provider adapter
- at least one frontier provider adapter
- request logging
- routing decision logging

Excludes:

- training pipeline
- promotion automation
- local specialist deployment automation

### Standard

Includes everything in `Minimal`, plus:

- candidate capture
- candidate approval and export
- evaluation workflows
- benchmark and economics reporting

Excludes:

- automated training and deployment loop

### Full

Includes everything in `Standard`, plus:

- dataset import pipeline
- LoRA and QLoRA training
- promotion gate
- deployment integration
- shadow and canary routing

## Profile Recommendation

- solo engineer: `Minimal`
- small team: `Standard`
- platform team: `Full`

## Rule

The implementation must not assume that all profiles are enabled at initial adoption.
