# Tasks: llmProxy Foundation

## Phase 1: Minimal Runtime Proxy

- create canonical repository structure
- implement configuration loader
- implement canonical database schema and migrations
- implement normalized chat, provider, and routing schemas
- implement one local provider adapter
- implement at least two frontier-provider adapters
- implement `POST /v1/chat/completions`
- implement request and routing persistence
- implement local Compose startup and smoke validation

## Phase 2: Teacher Ensemble

- implement multi-provider ensemble flow
- persist teacher outputs and judge critique
- persist ranked alternatives and fallback plans

## Phase 3: Training Candidate Pipeline

- implement candidate lifecycle
- implement approval/rejection flow
- implement JSONL export and manifest generation

## Phase 4: Dataset Pipeline

- implement import validation
- implement normalization, dedupe, and deterministic split
- implement dataset versioning

## Phase 5: Training Pipeline

- implement LoRA and QLoRA training orchestration
- persist metrics and artifacts

## Phase 6: Evaluation and Promotion

- implement benchmark loading and evaluation
- implement frontier baseline comparison
- implement economics reporting and promotion gate

## Phase 7: Deployment Integration

- implement local deployment targets
- implement proxy registration
- implement shadow, canary, fallback, and rollback

## Phase 8: Continuous Improvement

- implement KPI reporting
- implement event and outbox workflows
- implement local-specialist substitution reporting

## Execution Rule

Tasks must be executed in bounded iterations and validated according to the iteration protocol and test matrix.
