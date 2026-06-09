# scripts

Canonical script directory for local bootstrap, dataset, training, evaluation, and deployment helpers.

Primary local packaging entrypoints:

- `./scripts/install-local-macos.sh`
  - starts the local stack on macOS with Docker Desktop
  - creates `infra/compose/.env.local` if needed
  - picks up ignored `openai-api.key` and `anthropic-api.key` automatically when present
  - supports `--profile core|training|full`
  - supports `--report` for preflight and live provider-readiness reporting
  - supports `--report --json` for automation
  - supports `--install-deps` to install missing prerequisites when possible
  - `--with-training` remains a compatibility alias for `--profile full`
- `./scripts/start-local-macos.sh`
  - starts an existing local stack without rebuilding images
  - supports `--profile core|training|full`
  - supports `--json`
  - use this after a prior `stop`
- `./scripts/stop-local-macos.sh`
  - stops the local stack without removing containers
  - supports `--profile core|training|full`
  - supports `--json`
- `./scripts/teardown-local-macos.sh`
  - removes the local stack containers
  - supports `--profile core|training|full`
  - supports `--json`
  - `full` removes the entire Compose project and network
  - pass `--volumes` to remove volumes for full teardown, or anonymous volumes for partial teardown
- `./scripts/status-local-macos.sh`
  - summarizes lifecycle state, running profile, provider readiness, and local URLs
  - supports `--json`
