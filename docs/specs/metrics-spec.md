# Metrics Specification

## Purpose

This document defines the canonical formulas and data sources for the economics and routing KPIs in this project.

Unless explicitly overridden by a later approved revision, implementation agents should treat these formulas as normative.

## Measurement Principles

1. All monetary metrics must declare currency.
2. All cost metrics must identify whether they include only inference or blended operating cost.
3. All rate metrics must identify numerator, denominator, and exclusion rules.
4. Session-level and request-level metrics must be distinguishable.

## Event Sources

The implementation should derive metrics from persisted records such as:

- request log
- model response log
- routing decision log
- fallback event log
- provider pricing metadata
- training run metadata
- evaluation run metadata
- deployment and promotion records

## Canonical Cost Components

### Frontier Inference Cost

`frontier_inference_cost = input_token_cost + output_token_cost + provider_surcharge_if_any`

Derived from provider pricing metadata and request usage metadata.

### Local Inference Cost

`local_inference_cost = estimated_compute_cost + allocated_runtime_overhead`

The first implementation may estimate compute cost using configured per-hour runtime cost and average tokens-per-second utilization.

### Training Cost

`training_cost = gpu_compute_cost + storage_cost_for_training_artifacts + training_job_overhead`

### Evaluation Cost

`evaluation_cost = frontier_eval_cost + local_eval_cost + execution_harness_cost`

### Blended Task Cost

`blended_task_cost = inference_cost + allocated_training_amortization + allocated_evaluation_amortization`

Infrastructure overhead may be added if the operating policy chooses to include it.

## Canonical KPI Formulas

### Average Cost Per Request

`average_cost_per_request = total_request_cost / total_requests`

Exclude requests that never reached a provider because of pre-routing rejection.

### Average Cost Per Successful Request

`average_cost_per_successful_request = total_cost_of_successful_requests / total_successful_requests`

A successful request is one that returns a valid final response without terminal failure.

### Frontier Spend Per 100 Requests

`frontier_spend_per_100_requests = (total_frontier_inference_cost / total_requests) * 100`

### Local Spend Per 100 Requests

`local_spend_per_100_requests = (total_local_inference_cost / total_requests) * 100`

### Blended Spend Per 100 Requests

`blended_spend_per_100_requests = (total_blended_cost / total_requests) * 100`

### Local Routing Rate

`local_routing_rate = local_routed_requests / eligible_routed_requests`

Exclude requests that policy marks ineligible for local routing.

### Frontier Routing Rate

`frontier_routing_rate = frontier_routed_requests / total_routed_requests`

### Frontier-to-Local Substitution Rate

`frontier_to_local_substitution_rate = successful_local_substitutions / eligible_frontier_baseline_requests`

A successful local substitution is an eligible request served by a local specialist that remains within the accepted quality delta.

### Avoided Frontier Spend

`avoided_frontier_spend = sum(designated_frontier_counterfactual_cost - actual_local_route_cost)`

Computed only for eligible requests routed to an approved local specialist.

### Value-Per-Dollar

`value_per_dollar = normalized_quality_score / blended_task_cost`

The normalized quality score must be calculated from the domain benchmark rubric or production judge rubric on a `0.0` to `1.0` scale.

### Value-Per-Dollar Gain vs Frontier

`value_per_dollar_gain_vs_frontier = local_value_per_dollar / frontier_value_per_dollar`

### Quality Delta vs Frontier

`quality_delta_vs_frontier = frontier_baseline_score - local_specialist_score`

Smaller values are better. Negative values indicate the local specialist outperformed the baseline.

### Training Candidate Capture Rate

`training_candidate_capture_rate = captured_candidates / total_completed_requests`

### Approval Rate

`approval_rate = approved_candidates / reviewed_candidates`

### Export Yield Rate

`export_yield_rate = exported_candidates / approved_candidates`

### Dataset Quarantine Rate

`dataset_quarantine_rate = quarantined_records / imported_records`

### Training Success Rate

`training_success_rate = successful_training_runs / started_training_runs`

### Promotion Pass Rate

`promotion_pass_rate = approved_models / evaluated_models`

### Rollback Rate

`rollback_rate = rolled_back_deployments / deployed_models`

### Session Success Rate

`session_success_rate = successful_sessions / completed_sessions`

A successful session is one that achieves a valid final response path for all required critical requests in the session according to policy.

## Counterfactual Baseline Rules

Counterfactual frontier cost for avoided-spend calculations must use:

- the designated frontier baseline for the domain
- the same normalized prompt payload
- current configured price metadata or recorded benchmark price metadata

If exact live counterfactual execution is not performed, the system must mark the result as estimated.

## Reporting Granularity

Metrics must be reportable at:

- request level
- session level
- provider level
- model level
- domain level
- daily aggregate
- promotion cohort level

## Required Output Fields for KPI Reports

Every KPI report should include:

- time window
- metric name
- metric value
- formula version
- policy version
- sample size
- currency if applicable
- estimation flag if applicable
