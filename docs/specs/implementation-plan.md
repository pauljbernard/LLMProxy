# Implementation Plan

## Delivery Phases

### Phase 1: Minimal Runtime Proxy

Deliver:

- FastAPI service
- config loader
- database schema and migrations
- `POST /v1/chat/completions`
- one local model adapter
- at least two frontier-provider adapters
- request logging
- basic routing aliases
- routing decision logging
- provider capability registry
- initial cost and usage telemetry

### Phase 2: Teacher Ensemble

Deliver:

- multiple teacher adapters
- `POST /proxy/ensemble`
- judge prompt flow
- synthesized final answer
- response scoring
- ranked alternatives
- fallback-chain persistence

### Phase 3: Training Candidate Pipeline

Deliver:

- training candidate table
- candidate lifecycle
- approval and rejection endpoints
- JSONL export
- export manifest
- checksum generation

### Phase 4: Dataset Pipeline

Deliver:

- learner import endpoint
- manifest validation
- schema validation
- normalization
- deduplication
- deterministic splitting
- dataset versioning

### Phase 5: Training Pipeline

Deliver:

- LoRA trainer
- QLoRA trainer
- training config generation
- checkpointing
- metric capture
- artifact storage

### Phase 6: Evaluation and Promotion

Deliver:

- benchmark loader
- evaluation runner
- judge scoring
- code validation harness
- style scoring
- investment reasoning scoring
- promotion gate
- model registry
- designated frontier baseline comparison
- quality-delta and value-per-dollar reporting

### Phase 7: Deployment Integration

Deliver:

- deployment manager
- local runtime deployment adapter
- proxy model registration
- routing policy versioning
- shadow routing
- canary routing
- fallback behavior
- rollback endpoint
- promoted local-specialist eligibility rules

### Phase 8: Continuous Improvement Loop

Deliver:

- event outbox
- `dataset.exported` event flow
- learner import event handler
- model performance sampling
- teacher comparison sampling
- scheduled retraining hooks
- economics and KPI reporting
- avoided frontier spend reporting
- frontier-to-local substitution reporting

## Coding Agent Build Order

Future implementation agents should build in this order:

1. Create repository structure.
2. Implement configuration loader.
3. Implement canonical database schema and migrations from `database-schema-spec.md`.
4. Implement canonical request, response, provider, and routing-decision schemas from `api-schema-spec.md`.
5. Implement provider capability registry and pricing metadata support.
6. Implement local model provider adapter.
7. Implement at least two frontier-provider adapters.
8. Implement `POST /v1/chat/completions`.
9. Implement request, response, and routing-decision logging.
10. Implement simple routing aliases.
11. Implement session-aware routing context.
12. Implement provider ranking and fallback-chain logic.
13. Implement teacher ensemble.
14. Implement judge scoring.
15. Implement training candidate persistence.
16. Implement approval and rejection workflow.
17. Implement JSONL export.
18. Implement export manifest and checksum.
19. Implement learner dataset import.
20. Implement manifest validation.
21. Implement dataset validation.
22. Implement dataset normalization.
23. Implement deduplication.
24. Implement deterministic splitting.
25. Implement dataset versioning.
26. Implement LoRA training runner.
27. Implement QLoRA training runner.
28. Implement training metric capture.
29. Implement benchmark loader.
30. Implement evaluation runner.
31. Implement designated frontier baseline comparison.
32. Implement model registry.
33. Implement promotion gate with economics reporting.
34. Implement deployment manager.
35. Implement proxy model registration.
36. Implement routing policy versioning.
37. Implement shadow routing.
38. Implement canary routing.
39. Implement fallback behavior.
40. Implement rollback.
41. Implement integration events.
42. Implement KPI and avoided-spend reporting.
43. Add Docker Compose.
44. Add tests mirroring repository-standard module boundaries.
45. Add README with local startup instructions.

## Minimum Viable Integrated Flow

The first complete version is acceptable when:

1. A client can call `POST /v1/chat/completions` with `model=proxy-local`.
2. A client can call `POST /v1/chat/completions` with `model=proxy-teacher`.
3. A client can call `POST /proxy/ensemble` and receive a synthesized answer.
4. All requests and responses are persisted.
5. A response can be promoted to a training candidate.
6. A training candidate can be approved.
7. Approved candidates can be exported as JSONL.
8. Export manifests are valid.
9. The learner imports the export.
10. The learner creates a dataset version.
11. The learner launches a LoRA training run.
12. The learner launches a QLoRA training run.
13. Training metrics are stored.
14. Adapter artifacts are stored.
15. Evaluation benchmarks run.
16. Scores are stored.
17. Low-quality models fail promotion.
18. Qualified models pass promotion.
19. Approved models deploy to a local runtime.
20. Models register with the proxy.
21. The proxy supports shadow routing.
22. The proxy supports canary routing.
23. The proxy falls back on error.
24. Rollback restores the prior model.
25. New model responses can become future training candidates.
