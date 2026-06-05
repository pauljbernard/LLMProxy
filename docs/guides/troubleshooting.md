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
- the panel has not been refreshed yet

Try:

1. enter token `change-me`
2. click `Check Connection`
3. refresh the relevant panel
4. clear filters

## `/health` works but provider-backed chat fails

Health only proves the app is up. It does not prove every provider is configured.

Check:

- provider API keys
- provider base URLs
- local Ollama runtime availability if using local models

## The browser console works but pgAdmin looks empty

This usually means:

- you are looking at `public` only
- you are connected to a different server
- you are connected to a different database

## Worker or scheduler actions do not appear to do anything

Check:

- `Jobs & Events` panel
- `Operations` panel
- `/admin/api/ops/live`
- `/data/logs/operations.jsonl`

The action may have completed but not changed the currently filtered table.

## Live operations data seems stale

The `Operations` panel polls, but it is still a polling model, not push streaming.

Use:

- `Refresh Live Feed`
- `Refresh Jobs`
- `Refresh Events`

if you need an immediate update.
