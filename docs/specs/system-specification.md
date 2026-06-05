# System Specification

## High-Level Architecture

The system has three top-level areas:

1. Runtime proxy
2. Learner pipeline
3. Integration layer

Primary flow:

`Client -> OpenAI-compatible proxy -> classifier -> routing policy -> local models and/or teacher models -> judge/synthesizer -> training candidate recorder -> dataset export -> learner training pipeline -> evaluation and promotion gate -> model registry and deployment -> proxy routing update`

## Runtime Components

### API Gateway

OpenAI-compatible endpoints:

- `POST /v1/chat/completions`
- `GET /v1/models`
- `POST /v1/embeddings`

Native proxy endpoints:

- `POST /proxy/teacher`
- `POST /proxy/ensemble`
- `POST /proxy/evaluate`
- `POST /proxy/record`
- `GET /proxy/training-candidates`
- `POST /proxy/training-candidates/{id}/approve`
- `POST /proxy/training-candidates/{id}/reject`
- `POST /proxy/export/jsonl`
- `POST /proxy/models/register`
- `POST /proxy/models/{model_alias}/rollback`
- `GET /proxy/runs/{id}`
- `GET /health`
- `GET /metrics`

Supported initial proxy aliases:

- `proxy-auto`
- `proxy-local`
- `proxy-teacher`
- `proxy-ensemble`
- `proxy-coding`
- `proxy-architecture`
- `proxy-investment`

### Request Classifier

The classifier assigns:

- domain
- task type
- complexity
- privacy sensitivity
- tool need
- training value
- risk level

The initial implementation may be rule-based. Model-based classification is a later enhancement.

The classifier and routing layer together must also maintain session-aware context including:

- session objective
- workflow mode
- budget policy
- privacy mode
- latency tolerance
- prior-turn outcome signals
- user correction or dissatisfaction signals

### Routing Policy Engine

The routing engine chooses between local and frontier paths based on classification and policy.

Example policy logic:

- low-complexity coding requests route to a local coding model
- high-complexity architecture requests route to a teacher ensemble
- investment-analysis requests require stronger critique and review
- privacy-sensitive work prefers local-only routing
- training-valuable work passes through scoring and recording

The routing engine must also:

- rank candidate local and frontier models per request and per session
- consider provider health, price, latency, context-window fit, benchmark score, privacy compatibility, and tool compatibility
- support direct-vendor and hosted-provider targets
- persist ranked alternatives and routing rationale
- attach a fallback chain to the selected route

Representative routing outputs:

- selected provider
- selected model
- selected routing mode
- ranked alternatives
- decision rationale
- predicted cost class
- predicted latency class
- fallback plan

### Provider Adapter Layer

All providers implement a common normalized interface with support for:

- chat
- streaming chat
- embeddings
- model listing

The first-class provider families for the system are:

- OpenAI
- Anthropic
- Google Gemini
- xAI
- AWS Bedrock
- Azure OpenAI
- local runtimes

Normalized metadata must include:

- model
- provider
- provider_family
- latency_ms
- input_tokens
- output_tokens
- cost_estimate
- finish_reason
- raw_response_reference

Provider capability metadata should also include:

- supports_streaming
- supports_embeddings
- supports_tools
- max_context_tokens
- max_output_tokens
- privacy_class
- availability_status
- deployment_scope

### Teacher Ensemble

For eligible requests:

1. Send the normalized prompt to multiple teacher models.
2. Collect all responses.
3. Ask a judge model to compare or critique outputs.
4. Synthesize a best answer.
5. Persist all teacher responses and critiques.
6. Mark the synthesized result as a training candidate when eligible.

Output payload should include:

- final_answer
- teacher_outputs
- judge_critique
- chosen_rationale
- quality_score
- training_eligibility
- training_candidate_id

### Training Candidate Recorder

Persist:

- original prompt
- normalized prompt
- domain
- task type
- model outputs
- teacher critiques
- judge scores
- selected answer
- user feedback
- validation results
- approval status
- export status

## Learner Components

### Dataset Ingestion

Responsibilities:

- scan configured export locations
- import JSONL files
- validate manifest and checksums
- persist dataset metadata
- detect duplicate imports
- assign dataset version IDs

Supported import modes:

- file_drop
- api_import
- event_triggered_import

### Dataset Processing

The learner must support:

- record validation
- optional secret detection
- normalization
- exact, near, and semantic deduplication
- deterministic train/validation/test splitting
- curriculum or weighted sampling

Default split targets:

- train: 90%
- validation: 5%
- test: 5%

### Training Pipeline

Core training responsibilities:

- create training runs
- resolve base model and dataset version
- generate training config
- launch training jobs
- capture logs and metrics
- resume checkpoints
- store artifacts

Initial training modes:

- LoRA
- QLoRA

### Evaluation Pipeline

Every trained model must be evaluated before approval.

Evaluation types:

- automatic benchmark
- LLM judge
- code execution
- regression comparison
- style comparison
- latency benchmark
- memory benchmark

Initial evaluation domains:

- coding
- software_architecture
- common_lisp
- smalltalk
- agent_systems
- investment_analysis
- writing_style

### Code Validation Harness

For coding benchmarks, the system should be able to:

- clone or mount a repository
- apply generated patches
- run formatters
- run linters
- run tests
- capture logs
- revert the workspace

Initial validation commands:

- `pytest`
- `npm test`
- `mvn test`
- `gradle test`
- `sbcl` script execution

## Deployment and Operations

### Promotion Gate

A model may only be promoted when:

- required evaluations complete
- overall score meets threshold
- domain score meets threshold
- there are no critical regressions
- latency is acceptable
- memory use is acceptable
- artifacts are verified

### Deployment Strategies

- manual
- shadow
- canary
- production
- rollback

Shadow mode compares candidate behavior against production without serving it directly.

Canary mode serves limited real traffic to eligible requests.

Rollback restores the prior production model and reverts routing policy.

### Runtime Monitoring

Track:

- request count
- error rate
- timeout rate
- average latency
- p95 latency
- tokens per second
- teacher disagreement rate
- user retry rate
- fallback rate
- candidate capture rate
- per-provider spend
- per-model spend
- per-domain spend
- local-versus-frontier route mix
- avoided frontier spend

Quality signals:

- sampled judge score
- teacher comparison score
- code test pass rate
- style alignment score
- manual rejection rate

Economics and KPI calculations must follow the canonical formulas in `metrics-spec.md`.

## Data Model

Recommended first implementation uses one Postgres instance with separate schemas:

- `proxy.*`
- `learner.*`
- `integration.*`

Representative tables:

- `proxy.model_provider`
- `proxy.model_registry`
- `proxy.request_log`
- `proxy.model_response`
- `proxy.evaluation_result`
- `proxy.training_candidate`
- `learner.dataset_import`
- `learner.dataset_version`
- `learner.training_run`
- `learner.evaluation_run`
- `learner.model_registry`
- `integration.integration_event`
- `integration.integration_contract_version`
- `integration.routing_policy_version`

## Initial Repository Structure

The target implementation shape is:

```text
app/
  api/
  proxy/
  providers/
  datasets/
  training/
  evaluation/
  registry/
  deployment/
  integration/
  db/
  schemas/
  services/
  tests/
benchmarks/
scripts/
proxy_exports/
datasets/
exports/
models/
checkpoints/
reports/
docker-compose.yml
pyproject.toml
README.md
```
