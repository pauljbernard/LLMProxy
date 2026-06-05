# Asset Provenance and Licensing Specification

## Purpose

This document defines the minimum provenance and licensing metadata required for distilled assets, exported datasets, and promoted local specialists.

## Core Principle

The system must track where training assets came from, under what restrictions they were produced, and whether they are eligible for export, training, packaging, and deployment.

## Provenance Fields

The following fields should exist wherever training assets or model packages are persisted:

- `source_type`
- `source_provider_family`
- `source_provider_name`
- `source_model`
- `source_request_id`
- `source_session_id`
- `created_at`
- `created_by_system`
- `validation_method`
- `transformation_steps`

## Licensing and Usage Restriction Fields

The following fields should be available for training-candidate, export, and package metadata:

- `usage_restriction`
- `export_allowed`
- `training_allowed`
- `redistribution_allowed`
- `provider_terms_reference`
- `operator_policy_reference`
- `ownership_class`

## Ownership Classes

Supported ownership classes should include:

- `operator_owned`
- `provider_derived`
- `mixed`
- `restricted`

## Export Policy Rule

Assets may not be exported unless:

- provenance is present
- usage restriction is understood
- export policy allows it
- privacy and governance policy allows it

## Training Policy Rule

Assets may not be used for training unless:

- provenance metadata is complete enough to evaluate risk
- training policy allows it
- provider-derived restrictions do not block the intended use

## Model Package Rule

Every model package must carry forward the relevant provenance and licensing restrictions from the assets that contributed materially to its creation.

## Compliance Note

This specification does not make legal claims. It ensures the system retains the metadata needed for operators to make defensible policy decisions.
