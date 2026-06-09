# Observability Guide

`llmProxy` exposes its main operational inspection surface through `Observability` in the admin console, with `Runtime Control` handling queue execution and backlog processing.

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

Then work primarily from:

- `Observability > Events`
- `Observability > Topology`
- `Observability > Readiness`
- `Runtime Control`

### Events

`Observability > Events` is the canonical operational directory.

Use it to inspect:

- logs
- errors
- audit activity
- request traffic, via the `Traffic` preset
- training-relevant activity

The Events directory supports:

- saved views
- adaptive columns
- request-centric columns for traffic mode
- request-specific filters such as provider, model, pool, node, origin, and time window

Streamed chat requests are persisted after the stream completes. During an active stream, you may see request activity in logs before the final request and response rows appear in the request-backed event views.

### Topology

`Observability > Topology` provides the graph view of inbound listeners, proxy service, and outbound targets.

Use it to understand:

- how listeners map into the proxy
- which frontier and local targets are currently represented
- which configured targets are explicit policy routes vs implicit defaults/fallbacks

### Readiness

`Observability > Readiness` provides:

- provider and model readiness
- connectivity summaries
- local runtime visibility
- periodic monitor configuration
- vendor/model time-series performance trends

That is the main place to inspect:

- average first-response latency
- average total latency
- token/cost trends
- failure, fallback, redirect, cache, and SLA series

### Runtime Control

Use `Runtime Control` when you need to act on execution state rather than browse history.

That room covers:

- `Job Queue`
- `Pending Event Queue`
- manual worker runs
- manual scheduler runs
- event processing actions

Historical event browsing stays in `Observability > Events`.

## What you can observe

### Events and request traffic

The unified event directory can show:

- generic operational events
- request traffic rows
- training-relevant rows
- audit rows
- error rows

For request traffic rows, the directory can surface fields such as:

- requested model
- selected provider/model
- route context
- first-response latency
- total latency
- token usage
- cost
- prompt rollout state

### LLM readiness and trends

`Observability > Readiness` includes:

- provider readiness snapshots
- per-model readiness
- monitor status
- time-series charts and rollups at vendor/model scope

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

### Admin monitoring endpoints

```text
GET /admin/api/ops/summary
GET /admin/api/ops/events
GET /admin/api/ops/live
GET /admin/api/ops/llm-timeseries
GET /admin/api/ops/model-monitors
```

These endpoints require the bearer token.

## Debugging workflow

When debugging a problem:

1. Check `System` and `Observability > Readiness` first.
2. Review recent errors or traffic in `Observability > Events`.
3. Inspect `Observability > Topology` if the issue might be route- or target-related.
4. Inspect request detail from `Proxy` if the issue is request-specific.
5. Use `Runtime Control` if work is queued, stalled, or needs manual execution.
6. Check Postgres directly if you need persistent records across `proxy`, `learner`, and `integration`.

## Database visibility

The operational database uses these schemas:

- `proxy`
- `learner`
- `integration`

Do not inspect `public` alone and assume the system is empty.
