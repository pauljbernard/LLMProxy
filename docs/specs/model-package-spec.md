# Model Package Specification

## Purpose

This document defines the canonical packaging format for local specialists, adapters, and related metadata so models can be moved between environments and registries consistently.

## Package Scope

A model package must describe:

- the base model
- adapter or fine-tuned artifact paths
- contract compatibility
- benchmark and promotion metadata
- deployment target information
- provenance metadata

## Required Package Manifest Fields

Each model package manifest must include:

- `package_version`
- `model_registry_id`
- `model_alias`
- `base_model`
- `adapter_type`
- `artifact_format`
- `artifact_paths`
- `domains`
- `task_types`
- `quality_summary`
- `compatibility`
- `provenance`
- `created_at`

## Compatibility Block

The compatibility block must include:

- `model_contract_version`
- `learner_version`
- `compatible_proxy_versions`
- `runtime_targets`

## Quality Summary Block

The quality summary block should include:

- `overall_score`
- `domain_scores`
- `quality_delta_vs_frontier`
- `value_per_dollar_gain_vs_frontier`
- `promotion_status`

## Artifact Expectations

Artifacts may include:

- adapter weights
- adapter config
- tokenizer compatibility notes
- training config snapshot
- metrics snapshot
- evaluation report references

## Packaging Rule

A package must be self-describing enough that another environment can:

- determine compatibility
- understand intended domain use
- understand evaluation status
- understand provenance and restrictions

## Serialization Format

The manifest should be JSON or YAML. JSON is preferred for machine interchange.
