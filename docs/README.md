# llmProxy Documentation

This is the published documentation set for `llmProxy`.

`llmProxy` is not just a request router. It is a training proxy: a control plane that routes traffic, captures high-value interactions, turns approved work into training assets, and helps operators reduce recurring foundation-model spend by building and retaining small-model capability that they own.

Use this section when you want to install, operate, troubleshoot, and use the system. Use [docs/specs/README.md](./specs/README.md) when you need the deeper engineering and specification artifacts.

## Start Here

- [Product Overview](./guides/product-overview.md)
- [Quickstart](./guides/quickstart.md)
- [Operator Console Guide](./guides/operator-console.md)
- [Admin CLI Guide](./guides/admin-cli.md)

## Core Workflows

- [First Training Workflow](./guides/first-training-workflow.md)
- [Backend Command Integration](./guides/backend-command-integration.md)
- [Claude Code Gateway](./guides/claude-code-gateway.md)
- [Observability Guide](./guides/operations-monitoring.md)
- [Troubleshooting](./guides/troubleshooting.md)

## Reference

- [Configuration Reference](./reference/configuration.md)
- [API Usage Reference](./reference/api-usage.md)

## System URLs

- API base: `http://127.0.0.1:8000`
- Operator console: `http://127.0.0.1:8000/admin`
- Health: `http://127.0.0.1:8000/health`
- Metrics: `http://127.0.0.1:8000/metrics`

## Local Default Credentials

- Admin bearer token: `change-me`
- Host-side Postgres:
  - Host: `127.0.0.1`
  - Port: `15432`
  - Database: `llmproxy`
  - Username: `llm`
  - Password: `llm`
  - Maintenance database: `postgres`
