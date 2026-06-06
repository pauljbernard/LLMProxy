# Configuration Reference

This is the practical published reference for the most important `llmProxy` environment variables.

## Core runtime

| Variable | Purpose | Default |
|---|---|---|
| `LLMPROXY_ENV` | Environment label | `development` |
| `LLMPROXY_LOG_LEVEL` | Runtime log level | `INFO` |
| `LLMPROXY_API_HOST` | API bind host | `0.0.0.0` |
| `LLMPROXY_API_PORT` | API bind port | `8000` |
| `LLMPROXY_DATABASE_URL` | SQLAlchemy database URL | `postgresql+psycopg://llm:llm@localhost:5432/llmproxy` |
| `LLMPROXY_REDIS_URL` | Redis URL | `redis://localhost:6379/0` |
| `LLMPROXY_DATABASE_WAIT_TIMEOUT_SECONDS` | DB startup wait | `30` |
| `LLMPROXY_RUN_MIGRATIONS_ON_START` | Run Alembic on API startup | `true` |
| `LLMPROXY_PROVIDER_TIMEOUT_SECONDS` | Provider call timeout | `60.0` |
| `LLMPROXY_TRAINING_BACKEND_TIMEOUT_SECONDS` | training command timeout | `14400` |
| `LLMPROXY_EVALUATION_TIMEOUT_SECONDS` | evaluation command timeout | `3600` |
| `LLMPROXY_WORKER_INCLUDE_JOB_TYPES` | optional comma-separated worker lane include filter | unset |
| `LLMPROXY_WORKER_EXCLUDE_JOB_TYPES` | optional comma-separated worker lane exclude filter | unset |
| `LLMPROXY_FRONTIER_BASELINE_NAMES` | JSON map of domain to baseline model name | built-in defaults |
| `LLMPROXY_FRONTIER_BASELINE_SCORES` | JSON map of domain to baseline quality score | built-in defaults |
| `LLMPROXY_FRONTIER_BASELINE_COSTS` | JSON map of domain to baseline cost estimate | built-in defaults |

## Auth

| Variable | Purpose |
|---|---|
| `LLMPROXY_BEARER_TOKEN` | default operator bearer token |
| `LLMPROXY_TRUSTED_OPERATOR_TOKENS` | additional operator tokens |
| `LLMPROXY_AUTOMATION_TOKENS` | automation-only tokens |

## Providers

| Variable | Purpose |
|---|---|
| `LLMPROXY_OPENAI_API_KEY` | OpenAI API key |
| `LLMPROXY_OPENAI_BASE_URL` | OpenAI base URL |
| `LLMPROXY_OPENAI_MODEL` | default OpenAI model |
| `LLMPROXY_ANTHROPIC_API_KEY` | Anthropic API key |
| `LLMPROXY_ANTHROPIC_BASE_URL` | Anthropic base URL |
| `LLMPROXY_ANTHROPIC_MODEL` | default Anthropic model |
| `LLMPROXY_GOOGLE_API_KEY` | Google API key |
| `LLMPROXY_GOOGLE_BASE_URL` | Google base URL |
| `LLMPROXY_GOOGLE_MODEL` | default Google model |
| `LLMPROXY_XAI_API_KEY` | xAI API key |
| `LLMPROXY_XAI_BASE_URL` | xAI base URL |
| `LLMPROXY_XAI_MODEL` | default xAI model |
| `LLMPROXY_BEDROCK_REGION` | AWS Bedrock region |
| `LLMPROXY_BEDROCK_ACCESS_KEY_ID` | AWS access key |
| `LLMPROXY_BEDROCK_SECRET_ACCESS_KEY` | AWS secret |
| `LLMPROXY_BEDROCK_SESSION_TOKEN` | optional AWS session token |
| `LLMPROXY_BEDROCK_RUNTIME_MODEL_ID` | Bedrock runtime model id |
| `LLMPROXY_BEDROCK_MODEL` | logical Bedrock model label |
| `LLMPROXY_AZURE_OPENAI_API_KEY` | Azure OpenAI key |
| `LLMPROXY_AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint |
| `LLMPROXY_AZURE_OPENAI_API_VERSION` | Azure OpenAI API version |
| `LLMPROXY_AZURE_OPENAI_MODEL` | logical Azure model |
| `LLMPROXY_OLLAMA_BASE_URL` | Ollama endpoint |
| `LLMPROXY_OLLAMA_MODEL` | default Ollama model |

## Training and evaluation backends

| Variable | Purpose |
|---|---|
| `LLMPROXY_LORA_TRAINER_COMMAND` | command used for LoRA backend execution |
| `LLMPROXY_QLORA_TRAINER_COMMAND` | command used for QLoRA backend execution |
| `LLMPROXY_EVALUATION_COMMAND` | command used for benchmark evaluation execution |

See:

- [Backend Command Integration](../guides/backend-command-integration.md)

## Storage paths

| Variable | Purpose |
|---|---|
| `LLMPROXY_EXPORTS_PATH` | dataset exports |
| `LLMPROXY_DATASETS_PATH` | imported and split datasets |
| `LLMPROXY_MODELS_PATH` | model packages |
| `LLMPROXY_CHECKPOINTS_PATH` | training artifacts |
| `LLMPROXY_REPORTS_PATH` | KPI and report output |
| `LLMPROXY_LOGS_PATH` | structured operations logs |

## Recommended local values

For the Compose stack, see:

- [infra/compose/.env.example](../../infra/compose/.env.example)

For host-side database tools, use:

- Host: `127.0.0.1`
- Port: `15432`
- User: `llm`
- Password: `llm`
