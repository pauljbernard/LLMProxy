# Operations Monitoring

`llmProxy` now includes a dedicated operations monitoring surface in the admin console plus supporting APIs.

## Worker lanes

The default Compose deployment separates:

- `worker`: short-running operational jobs
- `training-worker`: long-running `training.run` jobs

This reduces the chance that one training run blocks:

- dataset imports
- KPI generation
- event follow-up work
- retraining planning

The lane behavior is controlled with:

- `LLMPROXY_WORKER_INCLUDE_JOB_TYPES`
- `LLMPROXY_WORKER_EXCLUDE_JOB_TYPES`

Example:

```text
LLMPROXY_WORKER_EXCLUDE_JOB_TYPES=training.run
```

and a dedicated training worker can run with:

```text
python3 -m app.runtime training-worker
```

## Visual monitoring

Open:

```text
http://127.0.0.1:8000/admin
```

Then open the `Operations` panel.

That panel provides:

- operations summary
- runtime metrics
- recent logs
- recent errors
- recent audit records
- live feed snapshot

The panel refreshes the live feed on demand and also polls while the panel is active.

Streamed chat requests are persisted after the stream completes. During an active stream, you may see request activity in logs before the final request/response records appear in the database-backed views.

## What you can observe

### Runtime summary

The summary includes:

- request count
- job counts by status
- event counts
- route counts
- recent error count
- recent audit count
- latest request ID
- latest evaluation run ID
- configured provider families

### Logs

Structured operational logs are written as JSON lines to:

```text
/data/logs/operations.jsonl
```

Log records include:

- timestamp
- level
- component
- category
- message
- structured data payload

### Errors

The error view filters log records where:

- `level = ERROR`
- or `level = CRITICAL`

Use this for quick triage before dropping into raw logs.

### Audit

The audit view captures privileged operational actions such as:

- job retries
- job cancellations
- manual scheduler runs
- manual worker runs
- event replay
- event processing
- deployment actions
- config mutations

## HTTP monitoring endpoints

### Health

```text
GET /health
```

Use for:

- basic liveness
- backend type confirmation
- configured provider families

### Metrics snapshot

```text
GET /metrics
```

Use for:

- current operational summary
- degraded-mode visibility if the DB is not reachable

### Admin operations endpoints

```text
GET /admin/api/ops/summary
GET /admin/api/ops/logs
GET /admin/api/ops/errors
GET /admin/api/ops/audit
GET /admin/api/ops/live
```

These endpoints require the bearer token.

## Debugging workflow

When debugging a problem:

1. Check `Overview` and `Operations` first.
2. Review recent errors in the `Operations` panel.
3. Review jobs and events in `Jobs & Events`.
4. Inspect request detail from the `Proxy` panel if the issue is request-specific.
5. Check Postgres directly if you need persistent records across `proxy`, `learner`, and `integration`.

## Database visibility

The operational database uses these schemas:

- `proxy`
- `learner`
- `integration`

Do not inspect `public` alone and assume the system is empty.
