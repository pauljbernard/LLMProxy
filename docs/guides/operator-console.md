# Operator Console

The operator console is the browser-based control surface for `llmProxy`.

URL:

```text
http://127.0.0.1:8000/admin
```

Default token:

```text
change-me
```

## Main rooms

### System

Use this room to:

- verify health
- inspect effective configuration
- validate runtime readiness
- update simple env-backed settings

### Proxy

Use this room to:

- run chat requests
- run streamed chat requests when the resolved provider supports streaming
- run ensemble requests
- run embeddings
- inspect request history
- inspect full request detail including routing, model responses, candidates, prompt lineage, and performance samples

Current streaming-capable providers include:

- `openai`
- `ollama`
- `anthropic`
- `google`
- `azure_openai`
- `xai`
- `bedrock`

If a request resolves to a provider without streaming support, the proxy returns a clear `501` instead of silently buffering or downgrading the request.

### Governance

Use this room to:

- inspect virtual keys
- review pricing policy
- inspect guardrails
- understand access scope and policy relationships

### Models

Use this room to:

- inspect vendor LLM catalogs
- inspect local runtime targets and custom packages
- onboard vendor or package capacity
- inspect and edit routing policies
- inspect deployment state and route exposure

Important model subviews:

- `LLMs`
- `Onboard`
- `Routing`
- `Deploy`

### Integrations

Use this room to:

- inspect live MCP, A2A, and REST endpoint surfaces
- review executable integration endpoints
- inspect reference guides without mixing them with live endpoints

### Prompt Library

Use this room to:

- inspect saved prompt families and versions
- compare active and challenger prompt versions
- run prompt canaries
- promote challengers
- inspect prompt usage metrics and rollout recommendations

### Data Pipeline

Use this room to:

- review training candidates
- approve or reject candidates
- create JSONL exports
- inspect exports
- import datasets
- inspect dataset imports and dataset versions

### Training

Use this room to:

- run training
- inspect training runs and evaluations
- review learning flow and runtime status
- inspect KPI and studio/runtime oversight

Important training subviews:

- `Runs & Evaluation`
- `Runtime & KPI`

### Observability

Use this room to:

- inspect the canonical event directory
- inspect request traffic through the `Traffic` event preset inside `Events`
- inspect routing/system topology
- inspect provider and runtime readiness
- inspect LLM performance time series and monitor configuration

Important observability subviews:

- `Events`
- `Topology`
- `Readiness`

### Runtime Control

Use this room to:

- inspect the job queue
- inspect pending internal event backlog
- retry, cancel, and process queued work
- run worker and scheduler iterations manually

Historical browsing lives primarily under `Observability > Events`; `Runtime Control` is for queue handling and execution control.

## Operator workflow tips

- If a table looks empty, click the room refresh button first.
- If you recently changed the token, click `Check Connection` again.
- Use row action buttons instead of copying IDs manually when available.
- Use `Observability > Events` as the canonical operational directory, then pivot into request detail, jobs, routing, or prompt lineage from there.
- Use `Observability > Readiness` for vendor/model health and time-series trends, not just `/health`.
