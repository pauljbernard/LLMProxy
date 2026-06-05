# Acceptance Criteria

## Phase Acceptance Criteria

### Phase 1

- IDEs or CLIs can call the proxy using an OpenAI-compatible endpoint.
- The proxy can route to a local model.
- The proxy can route to a teacher model.
- Requests and responses are stored.
- At least two frontier provider families can be called through normalized adapters.
- Routing decisions persist selected provider, selected model, and decision rationale.
- The application image can run locally with Postgres and Redis using the canonical environment contract.
- The local Compose manifest matches the canonical service, volume, and environment layout.
- CI validates application imports, tests, Docker build, and infrastructure syntax.
- Authenticated access exists for production API usage and protected operations are not left open by default.
- Phase 1 checklist items are all satisfied with no critical-path placeholders left in completed work.
- Minimum viable adoption can deliver proxy value without requiring the full learning loop.
- Implementation work follows the bounded iteration reporting protocol with explicit progress, next steps, and clarification requests when needed.
- Multi-day implementation work can resume cleanly using branch, PR, and session-resume rules without reconstructing context from scratch.

### Phase 2

- One prompt can be sent to multiple teachers.
- The proxy returns a synthesized best answer.
- Teacher outputs and judge critique are stored.
- Ranked alternatives and fallback plans are stored for ensemble-eligible requests.

### Phase 3

- Approved examples can be exported.
- Every export includes a manifest.
- Exported JSONL is ready for fine-tuning.

### Phase 4

- Proxy JSONL exports can be imported.
- Invalid records are quarantined.
- Valid records are versioned.
- Train, validation, and test splits are created.

### Phase 5

- A small model can be fine-tuned from imported data.
- Training metrics are persisted.
- Adapter artifacts are saved.

### Phase 6

- A trained adapter is evaluated.
- Scores are persisted.
- Passing models can be approved.
- Failing models are rejected.
- Previous production models remain available.
- Each promoted local specialist is evaluated against a designated frontier baseline for its domain.
- Promotion records include quality delta and value-per-dollar comparison versus the designated frontier baseline.

### Phase 7

- Approved models deploy locally.
- The learner registers models with the proxy.
- The proxy supports shadow routing.
- The proxy supports canary routing.
- The proxy falls back on error.
- Rollback restores the prior model.
- The proxy can route across required frontier-provider families and a promoted local specialist.
- The proxy records per-route cost and local-versus-frontier mix.
- The same release artifact can be deployed through the documented local, AWS, GCP, and Azure environment mappings.
- Kubernetes base manifests and environment overlays conform to the canonical manifest standard.
- OpenTofu environment entrypoints exist for local, AWS, GCP, and Azure using the required module structure.
- Release workflow includes migration validation, smoke verification, and rollback readiness.
- Production deployments satisfy minimum security gates for TLS, private data services, auditable privileged actions, and secret externalization.
- Performance SLOs and capacity review triggers are measurable from emitted telemetry.
- Minimal, Standard, and Full deployment profiles are all supportable without architecture changes.

### Phase 8

- New proxy exports can trigger a dataset version.
- New models can be compared against the current production model.
- Promotion remains gated.
- Local model responses can become future training candidates.
- At least one domain-specific local specialist can take real eligible traffic under policy control.
- The system can report avoided frontier spend attributable to local specialist routing.

## Promotion Gate Thresholds

Representative starting thresholds:

```yaml
promotion:
  min_overall_score: 0.85
  min_coding_pass_rate: 0.80
  min_architecture_score: 0.85
  min_style_score: 0.80
  max_regression_allowed: 0.02
  max_quality_delta_vs_frontier: 0.05
  min_value_per_dollar_gain_vs_frontier: 3.0
  min_local_route_share_for_promoted_domain: 0.60
```

A model may not enter `approved` unless evaluation succeeds.

A model may not enter `deployed` unless deployment health checks succeed.

A domain specialist may not enter `production` unless:

- it is compared against a designated frontier baseline
- it remains within the allowed quality delta for that domain
- it improves value-per-dollar materially
- the routing policy can identify eligible traffic for it

## Failure Handling

### Proxy Export Failure

- candidate statuses remain approved
- no dataset export event is emitted
- the error is logged
- retry is allowed

### Learner Import Failure

- the dataset is marked failed
- invalid records are quarantined
- the proxy is notified
- training is not started

### Training Failure

- the training run status becomes failed
- artifacts are retained for inspection
- proxy behavior remains unchanged
- a `training.failed` event is emitted

### Evaluation Failure

- the model cannot be promoted
- the training run status becomes evaluation failed
- proxy behavior remains unchanged

### Deployment Failure

- the model status becomes deployment failed
- proxy routing remains unchanged
- rollback is not required

### Runtime Failure

- the proxy falls back to a previous model or teacher
- a failure event is emitted
- rollback may be triggered

## Operational Definition of Done

This project is ready for initial implementation handoff when:

- the constitution is approved
- the requirements are specific enough to test
- core contracts are versioned
- the build order is explicit
- MVP flow and exit criteria are defined
- failure behavior is specified
- provider coverage strategy is explicit
- routing quality and economics are measurable
- specialization success is defined against frontier baselines
- deployment topology is defined for local, AWS, GCP, and Azure
- runtime environment, release, security, and operations standards are explicit
- IaC and deployment-manifest standards are explicit and prescriptive
- workflow governance, testing, CI/CD, data governance, and lifecycle policies are explicit
- threat model, authn/authz, secret lifecycle, supply-chain integrity, and security incident response expectations are explicit
- read order, artifact ownership, review gates, test matrix, and quantitative non-functional targets are explicit
- staged adoption, time-to-first-value, feature gating, and operator simplification rules are explicit
- engineer-agent collaboration, iteration planning, progress reporting, and decision logging rules are explicit
- branch lifecycle, PR management, and multi-session continuation rules are explicit
- future coding agents can begin implementation without re-deriving system intent
