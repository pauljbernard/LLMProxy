# Domain Specialization Plan

## Purpose

Local specialists should be built where they can plausibly outperform general frontier usage on value-per-dollar, privacy, or workflow fit.

The project should not attempt to specialize every domain at once.

## Initial Prioritization Rule

Initial specialization domains should be selected using:

- request frequency
- frontier spend concentration
- domain repeatability
- evaluation tractability
- privacy value
- likelihood that a smaller model can become highly competitive

## Initial Recommended Domain Order

1. `coding`
2. `software_architecture`
3. `writing_style`
4. `agent_systems`

These domains are preferred first because they are high-frequency, repetitive, benchmarkable, and likely to benefit from repository-specific or user-specific specialization.

## Deferred Domains

These domains should begin later or remain gated until stronger evaluation harnesses exist:

- `investment_analysis`
- `common_lisp`
- `smalltalk`

They remain strategically important, but they require stronger benchmark curation, risk controls, or larger volumes of high-quality examples.

## Designated Frontier Baselines

Each specialization domain must name a designated frontier comparison set.

Example baseline set:

- coding: top coding-capable frontier model plus one strong fallback comparator
- software_architecture: top reasoning model plus one alternate vendor model
- writing_style: top general writing model plus one style-strong comparator
- agent_systems: top reasoning or coding hybrid model plus one alternate comparator

The exact model names should be configurable because frontier offerings change quickly.

## Benchmark Strategy

Each specialization domain must define:

- benchmark corpus
- rubric
- pass thresholds
- comparison frontier set
- production sampling plan
- regression triggers

Benchmarks should include:

- offline curated tasks
- replay of approved training-candidate prompts excluded from training
- production shadow comparisons where safe

## Promotion Rule for Local Specialists

A local specialist may only be promoted for a domain if:

- it meets the domain quality threshold
- it stays within the allowed delta of the designated frontier baseline
- it improves value-per-dollar materially
- it passes domain-specific safety or correctness checks
- the routing policy can identify which requests are eligible for that specialist

## Domain Ownership and Dataset Discipline

Each domain must maintain:

- its own export targets
- its own benchmark group
- its own evaluation history
- its own promotion history
- its own rollback path

Datasets must remain separable by domain so that weak signals in one domain do not pollute another.

## Testable Outcome

The specialization strategy is successful only if at least one initial domain produces a local model that:

1. is trusted by the routing policy for real traffic
2. retains acceptable quality against frontier baselines
3. lowers blended cost materially
4. remains auditable and reversible
