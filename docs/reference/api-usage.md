# API Usage

`llmProxy` exposes both OpenAI-compatible endpoints and native operational endpoints.

The canonical machine-readable contract is:

- [OpenAPI](../contracts/openapi.yaml)

## Auth

Use bearer auth:

```http
Authorization: Bearer change-me
```

## OpenAI-compatible endpoints

### Chat completions

```http
POST /v1/chat/completions
```

Example:

```json
{
  "model": "proxy-auto",
  "messages": [
    {"role": "user", "content": "Review this patch."}
  ],
  "metadata": {
    "session_id": "sess_1",
    "domain_hint": "coding",
    "task_type_hint": "code_review"
  }
}
```

### Embeddings

```http
POST /v1/embeddings
```

Example:

```json
{
  "model": "text-embedding-3-small",
  "input": ["hello world"]
}
```

### Models

```http
GET /v1/models
```

## Native proxy endpoints

### Ensemble

```http
POST /proxy/ensemble
```

### Training candidates

```http
GET /proxy/training-candidates
POST /proxy/training-candidates/{id}/approve
POST /proxy/training-candidates/{id}/reject
```

### Export

```http
POST /proxy/export/jsonl
```

## Dataset, training, evaluation, deployment

### Dataset import

```http
POST /datasets/import
```

### Training

```http
POST /training/runs
GET /training/runs
```

### Evaluation

```http
POST /evaluation/runs
GET /evaluation/runs
GET /evaluation/kpis
```

### Deployment

```http
POST /deployment/models/{model_alias}/activate
POST /deployment/models/{model_alias}/rollback
GET /deployment/routing-policies
```

## Admin operations endpoints

The browser console uses admin APIs such as:

```http
GET /admin/api/config
GET /admin/api/proxy/requests
GET /admin/api/jobs
GET /admin/api/events
GET /admin/api/ops/summary
GET /admin/api/ops/live
```

These endpoints are intended for operator tooling rather than public end-user integration.
