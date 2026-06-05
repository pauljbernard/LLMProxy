# Quickstart

This guide gets a local `llmProxy` stack running, opens the operator UX, and verifies the basic control surfaces.

## Prerequisites

- Docker Desktop running
- Python 3.11+ if you want to use the host-side CLI
- A free local port for:
  - `8000` for the API and operator console
  - `15432` for the Compose Postgres database
  - `6379` for Redis

## Start the stack

From the repository root:

```bash
docker compose -f infra/compose/docker-compose.yml up -d
```

Check status:

```bash
docker compose -f infra/compose/docker-compose.yml ps
```

## Verify health

Open:

- API health: `http://127.0.0.1:8000/health`
- Operator console: `http://127.0.0.1:8000/admin`

Expected health response shape:

```json
{
  "status": "ok",
  "environment": "local",
  "database_backend": "postgresql"
}
```

## Sign into the operator console

The default bearer token is:

```text
change-me
```

Enter the token in the top bar of the operator console and click:

1. `Save Token`
2. `Check Connection`

## Use the admin CLI

If the package entrypoint is installed:

```bash
llmproxy-admin --help
```

Otherwise:

```bash
python3 -m app.cli --help
```

Basic checks:

```bash
python3 -m app.cli health
python3 -m app.cli config show
python3 -m app.cli models list --proxy
python3 -m app.cli jobs list
```

## Connect a database tool

For pgAdmin or host-side `psql`, use:

```text
Host: 127.0.0.1
Port: 15432
Database: llmproxy
Username: llm
Password: llm
Maintenance database: postgres
```

Important: application tables are not in `public` only. Inspect:

- `proxy`
- `learner`
- `integration`

## What to do next

- To operate the system visually, use [Operator Console](./operator-console.md)
- To operate the system from the terminal, use [Admin CLI](./admin-cli.md)
- To walk the learning loop end to end, use [First Training Workflow](./first-training-workflow.md)
- To monitor live activity, use [Operations Monitoring](./operations-monitoring.md)
