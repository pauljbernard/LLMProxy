# Requirements

## Functional Requirements

### Runtime Proxy

The system must:

- expose `POST /v1/chat/completions`
- expose `GET /v1/models`
- optionally expose `POST /v1/embeddings`
- support streaming responses
- route requests to local or remote providers
- preserve request and response metadata
- record selected interactions as training candidates

Supported local runtimes should include one or more of:

- Ollama
- llama.cpp server
- vLLM
- LM Studio
- MLX-LM or MLX server

Supported teacher/provider adapters should include:

- OpenAI
- Anthropic
- Google Gemini
- xAI
- AWS Bedrock
- Azure OpenAI
- OpenAI-compatible providers
- provider-specific metadata normalization across direct and hosted variants
- configurable fallback chains across providers

### Request Understanding and Routing

Every request must be classified by:

- domain
- task type
- complexity
- privacy sensitivity
- tool need
- training value
- risk level

Every session must also maintain routing context for:

- session objective
- user preferences
- budget policy
- latency tolerance
- privacy mode
- prior turn history
- prior fallback or failure history
- user dissatisfaction or correction signals

Initial domains:

- coding
- software_architecture
- common_lisp
- smalltalk
- agent_systems
- investment_analysis
- writing
- general

Initial task types:

- code_generation
- code_review
- bug_fix
- architecture_decision
- investment_thesis
- comparison
- refactoring
- documentation
- question_answer

The routing engine must support these modes:

- local_only
- frontier_single
- frontier_ensemble
- local_then_teacher
- teacher_then_local
- judge_only
- record_only

The routing engine must also:

- rank local and frontier candidates per request and session
- consider provider health, cost, latency, privacy, context-window fit, and benchmark performance
- support direct vendor and hosted-provider targets
- persist routing rationale and ranked alternatives
- support configurable fallback chains
- support local-specialist preference when a promoted local model is within accepted quality bounds

### Teacher Ensemble and Evaluation

The system must support:

- querying multiple teacher models for selected tasks
- collecting and preserving all teacher outputs
- synthesizing a best answer
- scoring responses with judge models and rule-based validators
- preserving judge critiques and chosen rationale
- comparing local specialists against designated frontier baselines by domain

Evaluation dimensions must include:

- correctness
- completeness
- technical depth
- architectural soundness
- clarity
- style match
- testability
- risk awareness
- domain fit

For code-oriented work, evaluation should also cover:

- compile success where applicable
- test success
- minimal-change preference
- repository convention alignment
- security risk
- performance risk

### Training Candidate Pipeline

The system must:

- persist original and normalized prompts
- persist model outputs, critiques, scores, and validation results
- manage a lifecycle for candidate states
- support explicit approval and rejection workflows
- prevent export unless policy and quality checks pass

Candidate lifecycle states:

- captured
- scored
- needs_review
- approved
- rejected
- exported
- imported
- trained
- retired

### Dataset Export and Import

The proxy must:

- export approved examples as JSONL
- emit a manifest for every export
- support domain-specific export targets
- include provenance and validation metadata

The learner must:

- import proxy exports
- validate manifest and checksums
- validate schema and record quality
- quarantine invalid records
- assign deterministic dataset version IDs
- normalize, deduplicate, and split imported data

### Training Pipeline

The learner must:

- support LoRA fine-tuning
- support QLoRA fine-tuning
- support multiple base models
- support repeatable training runs
- support checkpointing
- persist logs, metrics, and artifacts
- register trained adapters

Initial training modes:

- lora
- qlora

Future modes:

- full_finetune
- continued_pretraining
- dpo

### Evaluation and Promotion

The system must:

- evaluate every trained model before promotion
- compare trained models against base and prior local versions
- compare trained local specialists against designated frontier baselines for the intended domain
- support automatic benchmarks and judge scoring
- support code validation harnesses
- prevent bad models from promotion

### Deployment and Monitoring

The system must:

- publish approved models to local runtimes
- register deployed models with the proxy
- support model aliases
- support routing by domain and task type
- support shadow deployment
- support canary deployment
- support production promotion
- support rollback
- preserve prior production models
- monitor runtime metrics and quality signals
- track per-provider, per-model, and per-domain cost
- track local-versus-frontier route mix
- track frontier-to-local substitution success
- report avoided frontier spend and local specialist ROI

## Non-Functional Requirements

- Python 3.11+ is the preferred initial implementation platform.
- FastAPI is the preferred first runtime framework.
- Postgres is the primary system of record.
- Contracts must be versioned and compatibility-checked.
- Secrets must be stored outside source code.
- Logs must redact secrets.
- Request size, timeout, and rate limits must be configurable.
- The system must support local-only mode.
- The first local version may use simple bearer-token auth.
- Routing and economics policies must be measurable through persisted telemetry.

## Preferred Initial Stack

- FastAPI
- SQLAlchemy
- Alembic
- Pydantic
- Postgres
- pgvector
- Redis
- Celery or RQ
- Transformers
- PEFT
- TRL
- Datasets
- Accelerate
- bitsandbytes
- PyTorch
- Unsloth

## Target Model Families

- Qwen Coder
- Qwen general models
- DeepSeek Coder
- Llama
- Mistral
- Gemma
- Phi
