# llmProxy Documentation

This is the published documentation set for `llmProxy`.

Use this section when you want to install, operate, troubleshoot, and use the system. Use [docs/specs/README.md](./specs/README.md) when you need the deeper engineering and specification artifacts.

## Start Here

- [Product Overview](./guides/product-overview.md)
- [Quickstart](./guides/quickstart.md)
- [Operator Console Guide](./guides/operator-console.md)
- [Admin CLI Guide](./guides/admin-cli.md)

## Core Workflows

- [First Training Workflow](./guides/first-training-workflow.md)
- [Backend Command Integration](./guides/backend-command-integration.md)
- [Operations Monitoring](./guides/operations-monitoring.md)
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
