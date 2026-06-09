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
./scripts/install-local-macos.sh
```

This is the canonical local bootstrap path on macOS. It creates `infra/compose/.env.local` if needed, picks up ignored local provider key files when present, builds the core stack, starts it, and waits for health.

You can also choose an explicit service profile:

```bash
./scripts/install-local-macos.sh --profile core
./scripts/install-local-macos.sh --profile training
./scripts/install-local-macos.sh --profile full
```

If you also want the training services immediately and prefer the older flag:

```bash
./scripts/install-local-macos.sh --with-training
```

`--with-training` remains as a compatibility alias for `--profile full`.

To print a local preflight plus the current live provider-readiness report:

```bash
./scripts/install-local-macos.sh --report
```

To emit the same report as JSON for automation:

```bash
./scripts/install-local-macos.sh --report --json
```

To let the installer bootstrap missing prerequisites when possible:

```bash
./scripts/install-local-macos.sh --install-deps
```

Rerunning the installer with a different profile reconciles the optional services to that profile.

If you need the manual Compose path instead:

```bash
docker compose -f infra/compose/docker-compose.yml up -d
```

Check status:

```bash
docker compose -f infra/compose/docker-compose.yml ps
```

To stop the stack later:

```bash
./scripts/stop-local-macos.sh
```

To stop it and emit JSON for automation:

```bash
./scripts/stop-local-macos.sh --json
```

To start it again later without rebuilding:

```bash
./scripts/start-local-macos.sh --profile core
```

To start it again and emit JSON for automation:

```bash
./scripts/start-local-macos.sh --profile core --json
```

To inspect lifecycle state and current provider readiness:

```bash
./scripts/status-local-macos.sh
```

To tear it down completely:

```bash
./scripts/teardown-local-macos.sh
```

To tear it down and emit JSON for automation:

```bash
./scripts/teardown-local-macos.sh --json
```

To partially tear down a profile:

```bash
./scripts/teardown-local-macos.sh --profile training
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
- To monitor live activity, use the [Observability Guide](./operations-monitoring.md)
