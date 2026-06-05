# Benchmark Artifact Specification

## Purpose

This document defines the canonical artifact format for benchmarks so evaluations are portable, reproducible, and comparable across runs and environments.

## Benchmark Artifact Structure

Each benchmark artifact should contain:

- `benchmark_manifest.json`
- one or more benchmark data files
- optional rubric files
- optional fixture assets

## Benchmark Manifest Fields

Required fields:

- `benchmark_version`
- `benchmark_group`
- `domain`
- `task_types`
- `record_count`
- `scoring_method`
- `source`
- `created_at`

Optional but recommended:

- `frontier_baseline_set`
- `holdout_policy`
- `artifact_hash`

## Benchmark Record Fields

Each benchmark record should include:

- `benchmark_id`
- `domain`
- `task_type`
- `prompt`
- `reference_answer`
- `rubric`

Optional fields:

- `input_files`
- `expected_tests`
- `tags`

## Holdout Rule

Benchmark artifacts must remain separate from training datasets and must be traceable as holdout or validation assets.

## Evaluation Output Compatibility

Evaluation reports should be able to reference:

- `benchmark_version`
- `benchmark_group`
- `frontier_baseline_set`
- `scoring_method`

## Portability Rule

Benchmark artifacts must be environment-independent and usable in local or cloud evaluation runs without semantic change.
