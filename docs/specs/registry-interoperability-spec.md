# Registry Interoperability Specification

## Purpose

This document defines the future-facing contract hooks needed if `llmProxy` later exchanges specialist models with external registries or enterprise catalog systems.

## Current Scope

This project does not implement a distributed or global registry in the first version.

It does, however, define the metadata required to interoperate later.

## Required Interoperability Metadata

Registry-facing exports should be able to provide:

- `model_registry_id`
- `model_alias`
- `package_version`
- `domains`
- `task_types`
- `quality_summary`
- `compatibility`
- `provenance`
- `usage_restriction`
- `ownership_class`

## Import Expectations

If an external specialist package is imported later, the system should be able to validate:

- compatibility
- provenance completeness
- usage restrictions
- benchmark evidence
- runtime target compatibility

## Non-Goal

This document does not require:

- distributed registry consensus
- external marketplace integration
- multi-organization trust federation

It only ensures current packages and metadata are future-compatible with those possibilities.
