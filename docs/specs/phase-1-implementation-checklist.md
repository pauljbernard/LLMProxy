# Phase 1 Implementation Checklist

Phase 1 is not complete unless every item below is satisfied.

- repository structure matches `repository-standard.md`
- `pyproject.toml` supports application startup and tests
- `POST /v1/chat/completions` is implemented
- `GET /v1/models` is implemented
- configuration loader is implemented
- canonical database migration applies successfully
- request persistence is implemented
- routing decision persistence is implemented
- one local provider adapter is implemented
- at least two frontier-provider adapters are implemented
- authenticated access exists for production API usage
- OpenAPI and JSON Schemas are updated if behavior changed
- unit and integration tests exist for implemented paths
- local Compose startup works with canonical environment variables
- health check passes after startup
