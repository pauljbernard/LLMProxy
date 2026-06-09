# Troubleshooting

## pgAdmin connects but only shows `public`

You are likely connected to the wrong Postgres instance or database.

For the `llmProxy` Compose database, use:

- Host: `127.0.0.1`
- Port: `15432`
- Database: `llmproxy`
- Username: `llm`
- Password: `llm`
- Maintenance database: `postgres`

Inspect these schemas:

- `proxy`
- `learner`
- `integration`

## `role "llm" does not exist`

You are hitting the wrong PostgreSQL server, often because another local Postgres is already using `5432`.

Use port `15432` for the `llmProxy` Compose database.

## The admin console shows no rows

Possible causes:

- token is not saved
- page loaded before the rows existed
- filters are hiding rows
- the current preset or history scope is excluding the rows you expect

Try:

1. enter token `change-me`
2. click `Check Connection`
3. refresh the relevant room
4. clear filters or reset the saved view
5. if you are in `Observability > Events`, check whether you are viewing `Active Only`, `Historical Only`, or a non-default preset

## `/health` works but provider-backed chat fails

Health only proves the app is up. It does not prove every provider is configured or every discovered model is invokable.

Check:

- provider API keys
- provider base URLs
- model-specific readiness under `Observability > Readiness`
- explicit routing policy versus fallback behavior
- local Ollama runtime availability if using local models

## The browser console works but pgAdmin looks empty

This usually means:

- you are looking at `public` only
- you are connected to a different server
- you are connected to a different database

## Worker or scheduler actions do not appear to do anything

Check:

- `Runtime Control > Job Queue`
- `Runtime Control > Pending Event Queue`
- `Observability > Events`
- `/admin/api/ops/live`
- `/data/logs/operations.jsonl`

The action may have completed but not changed the currently filtered directory or queue view.

## I cannot find request traffic anymore

Request traffic now lives inside `Observability > Events`.

Use one of these:

- the `Traffic` preset
- `Traffic Columns`
- request-specific filters such as provider, model, pool, node, origin, or time window

There is no longer a separate primary `Traffic` table.

## Live operational data seems stale

The console still uses refresh/polling behavior, not push streaming.

Use:

- `Refresh Summary`
- `Refresh Live Feed`
- `Refresh Topology`
- `Refresh Readiness`

depending on the room you are in.

If the problem is queue state rather than historical browsing, also refresh `Runtime Control`.

## A model is exposed but not healthy

Those columns mean different things.

- `Exposed` means the model is part of the proxy-visible catalog.
- `Explicit Route` means an explicit policy row references it.
- `Ready` means the readiness probe for that model succeeded.

A discovered model can be exposed by default and still be `Unavailable` if the upstream provider rejects the probe or the adapter needs model-specific request-shape handling.

## Claude Code or Anthropic gateway requests land on the wrong target

Check:

1. `GET /health` to confirm the intended provider is healthy.
2. `POST /v1/messages/count_tokens` with your token to verify gateway auth.
3. `Models > Routing` for explicit redirects or policy routes.
4. `Observability > Events` request detail to confirm the actual selected provider/model.

Remember that a successful gateway call only proves the inbound Anthropic-compatible surface works; it does not by itself prove the request landed on Anthropic.
