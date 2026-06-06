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

## Panels

### Overview

Use this panel to:

- verify health
- inspect effective configuration
- validate runtime readiness
- update simple env-backed settings

### Proxy

Use this panel to:

- run chat requests
- run streamed chat requests when the resolved provider supports streaming
- run ensemble requests
- run embeddings
- inspect request history
- inspect full request detail including routing, model responses, candidates, and performance samples

Current streaming-capable providers:

- `openai`
- `ollama`
- `anthropic`
- `google`
- `azure_openai`
- `xai`
- `bedrock`

If a request resolves to a provider without streaming support, the proxy returns a clear `501` instead of silently buffering or downgrading the request.

### Models & Deployment

Use this panel to:

- inspect available proxy models
- inspect local registered packages
- inspect routing policies
- register a local model package
- activate a model in `shadow`, `canary`, or `production`
- roll back an active model

### Candidates, Datasets & Training

Use this panel to:

- review training candidates
- approve or reject candidates
- create JSONL exports
- inspect exports
- import datasets
- inspect dataset imports and dataset versions
- start training runs
- inspect training runs

### Evaluation & KPI

Use this panel to:

- run evaluations for training runs
- inspect evaluation runs
- review KPI output
- prepare approved evaluations for deployment

### Operations

Use this panel to:

- monitor runtime summary and metrics
- inspect recent logs
- inspect recent errors
- inspect audit activity
- review the live feed snapshot

### Jobs & Events

Use this panel to:

- inspect queued and completed jobs
- retry or cancel jobs
- inspect integration events
- replay events
- run worker and scheduler iterations manually

## Operator workflow tips

- If a table looks empty, click the panel refresh button first.
- If you recently changed the token, click `Check Connection` again.
- Use the row action buttons instead of copying IDs manually when available.
- Use the Operations panel while triggering actions in other panels to see live system effects.
