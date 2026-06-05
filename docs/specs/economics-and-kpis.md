# Economics and KPIs

## Purpose

The project goal is not merely to train local models. The goal is to reduce long-run operating cost while maintaining or improving results in targeted domains.

This document defines measurable success criteria for that objective.

## Economic Model

The learning loop should convert expensive frontier interactions into cheaper future local inference for repeatable problem classes.

The project must therefore measure:

- frontier runtime spend
- local runtime cost
- training cost
- evaluation cost
- storage and infrastructure cost
- cost per successful task
- cost per accepted training candidate
- cost recovery period for each promoted local specialist

## Core KPIs

### Proxy KPIs

- average cost per request
- average cost per successful request
- average latency per request
- p95 latency
- fallback rate
- provider failure rate
- session success rate

### Learning-Loop KPIs

- training-candidate capture rate
- approval rate
- export yield rate
- dataset quarantine rate
- training success rate
- promotion pass rate
- rollback rate

### Cost-Reduction KPIs

- frontier spend per 100 requests
- local spend per 100 requests
- blended spend per 100 requests
- local-routing rate
- frontier-routing rate
- frontier-to-local substitution rate
- frontier cost avoided through successful local substitution
- training amortization period

### Quality KPIs

- benchmark score by domain
- frontier baseline score by domain
- local specialist score by domain
- local specialist win rate versus chosen frontier baseline
- user retry rate
- user correction rate
- sampled judge score

## Testable Economic Targets

These are starting targets and should be tuned later with real usage data:

1. For at least one initial specialization domain, the promoted local specialist must achieve at least `95%` of the benchmark score of the designated frontier baseline.
2. For at least one initial specialization domain, the promoted local specialist must outperform the designated frontier baseline on value-per-dollar by at least `3x`.
3. For at least one initial specialization domain, at least `60%` of eligible requests should route locally after specialist promotion without violating quality thresholds.
4. The proxy must report blended runtime cost and avoided frontier spend at the session, daily, and model levels.
5. Each promoted local specialist must have a documented training cost and estimated break-even point.

## Domain-Level ROI Requirement

A local specialist should only remain in production if:

- its benchmark and sampled production quality remain within the permitted quality delta of its designated frontier baseline
- its routed workload is large enough to justify ongoing maintenance
- it produces measurable cost avoidance or privacy value

## Promotion Economics Gate

A model may not be promoted to production unless all of the following are true:

- quality thresholds are satisfied
- runtime latency is acceptable
- projected cost per successful task improves materially for its intended domain or privacy mode
- the designated frontier comparison set has been evaluated
- expected routing volume is sufficient to justify deployment

## Reporting Requirements

The system must produce reports for:

- per-provider spend
- per-model spend
- per-domain spend
- local versus frontier route mix
- quality versus cost tradeoff
- promotion ROI summary
- rollback and regression summary

## Anti-Goal

It is not enough for the project to produce a functional local model. The project succeeds only when the local model is operationally useful and economically justified in its target domain.
