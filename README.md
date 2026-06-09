# llmProxy

This repository uses a SpecKit-inspired, spec-driven development approach and now contains both the implementation codebase and the governing specification set.

The primary implementation baseline is documented through a custom SpecKit-aligned specification set in [specs/001-llmproxy-foundation](./specs/001-llmproxy-foundation) and the extended reference library in [docs/specs](./docs/specs/README.md).

Initial source material is [baseline.txt](./baseline.txt).

Future coding agents should begin with the documents in `docs/specs/` before starting implementation.

## Strategic Objectives

The strategic objective of `llmProxy` is to convert repeated high-value frontier-model usage into durable, owned, local capability.

This project exists to:

- provide an OpenAI-compatible proxy for existing tools, agents, IDEs, and CLIs
- route requests across local runtimes and frontier providers based on task, session, privacy, cost, and quality needs
- capture valuable interactions as governed training assets instead of letting them disappear after inference
- train and evaluate domain-specific local specialists that can take over appropriate classes of work
- shift a meaningful share of token usage from expensive frontier inference to cheaper, private, fine-tuned local models where quality remains acceptable
- preserve auditability, rollback, security, and economic discipline throughout that learning loop

The project is not trying to build a frontier foundation model or a full AI ecosystem. It is trying to build one enabling component: a production-capable local-first proxy and learning system that makes specialized model ownership practical.

## Architecture

![llmProxy architecture](docs/assets/architecture-diagram.svg)

## Documentation

Published user and operator documentation is available in [docs/README.md](./docs/README.md).

Recommended starting points:

- [Product Overview](./docs/guides/product-overview.md)
- [Quickstart](./docs/guides/quickstart.md)
- [Operator Console](./docs/guides/operator-console.md)
- [Admin CLI](./docs/guides/admin-cli.md)
- [Operations Monitoring](./docs/guides/operations-monitoring.md)
- [First Training Workflow](./docs/guides/first-training-workflow.md)
- [Backend Command Integration](./docs/guides/backend-command-integration.md)
- [Claude Code Gateway](./docs/guides/claude-code-gateway.md)
- [Troubleshooting](./docs/guides/troubleshooting.md)
- [Configuration Reference](./docs/reference/configuration.md)
- [API Usage](./docs/reference/api-usage.md)

## Local Install On macOS

For a fresh local checkout on macOS with Docker Desktop, the canonical bootstrap path is:

```bash
./scripts/install-local-macos.sh
```

What it does:

- verifies you are on macOS
- verifies Docker Desktop is available and ready
- creates `infra/compose/.env.local` if it does not exist
- automatically picks up ignored local secrets from:
  - `openai-api.key`
  - `anthropic-api.key`
- builds and starts the selected local Compose profile
- waits for the API health endpoint to become ready
- can install missing prerequisites when invoked with `--install-deps`

Available install profiles:

```bash
./scripts/install-local-macos.sh --profile core
./scripts/install-local-macos.sh --profile training
./scripts/install-local-macos.sh --profile full
```

Profile behavior:

- `core`: `postgres`, `redis`, `jaeger`, `api`, `worker`, `scheduler`
- `training`: `core` plus `training-worker`
- `full`: `training` plus `unsloth-studio`

If you also want the training services on first boot:

```bash
./scripts/install-local-macos.sh --with-training
```

`--with-training` remains as a compatibility alias for `--profile full`.

To print a packaging preflight and current live provider-readiness report:

```bash
./scripts/install-local-macos.sh --report
```

To emit the same report as machine-readable JSON:

```bash
./scripts/install-local-macos.sh --report --json
```

To let the installer bootstrap missing prerequisites when possible:

```bash
./scripts/install-local-macos.sh --install-deps
```

Rerunning the installer with a different profile reconciles the optional services to that profile.

To stop the local stack:

```bash
./scripts/stop-local-macos.sh
```

To stop it and emit a machine-readable result:

```bash
./scripts/stop-local-macos.sh --json
```

To start a previously stopped stack without rebuilding:

```bash
./scripts/start-local-macos.sh --profile core
```

To start it and emit a machine-readable result:

```bash
./scripts/start-local-macos.sh --profile core --json
```

To inspect current lifecycle state, provider readiness, and exposed local URLs:

```bash
./scripts/status-local-macos.sh
```

To tear the stack down:

```bash
./scripts/teardown-local-macos.sh
```

To tear it down and emit a machine-readable result:

```bash
./scripts/teardown-local-macos.sh --json
```

To partially tear down just the training profile:

```bash
./scripts/teardown-local-macos.sh --profile training
```

To tear the full stack down and remove Compose volumes:

```bash
./scripts/teardown-local-macos.sh --profile full --volumes
```

## Operator CLI

`llmProxy` includes a utilitarian admin CLI for configuration inspection and day-to-day operations.

The CLI entrypoint is:

```bash
llmproxy-admin --help
```

If you have not installed the package script yet, you can run it directly from the repo:

```bash
python3 -m app.cli --help
```

Common commands:

```bash
python3 -m app.cli health
python3 -m app.cli config show
python3 -m app.cli config validate
python3 -m app.cli models list --proxy
python3 -m app.cli models local
python3 -m app.cli deploy policies
python3 -m app.cli candidates list
python3 -m app.cli training list
python3 -m app.cli evaluation list
python3 -m app.cli jobs list
python3 -m app.cli events list
python3 -m app.cli scheduler run-once
```

Configuration file updates can be written to an env file directly:

```bash
python3 -m app.cli config set LLMPROXY_OPENAI_API_KEY your-key-here --env-file .env.local
```

To validate the local stack with Compose manually, start the services and then use the CLI against the running environment:

```bash
docker compose -f infra/compose/docker-compose.yml up -d --no-build
python3 -m app.cli health
python3 -m app.cli models list --proxy
python3 -m app.cli jobs list
```

The Compose Postgres service is published on host port `15432` to avoid conflicts with any other local PostgreSQL instance already using `5432`.
For host-side tools such as pgAdmin, use:

```text
Host: 127.0.0.1
Port: 15432
Database: llmproxy
Username: llm
Password: llm
Maintenance database: postgres
```

## Operator Console

`llmProxy` also includes a visual operator console served by the API runtime:

```bash
http://127.0.0.1:8000/admin
```

The console is designed to cover the same core operator surface as the admin CLI:
- health and configuration
- proxy chat, ensemble, embeddings, and request history
- model registration and deployment control
- candidate review, exports, dataset import, and training
- evaluation, KPI review, jobs, events, and scheduler actions

The browser console uses the same bearer-token model as the API and expects an operator or automation token to be entered in the top bar before making authenticated requests.

## License

This repository is licensed under the Apache License, Version 2.0. See [LICENSE](./LICENSE).
