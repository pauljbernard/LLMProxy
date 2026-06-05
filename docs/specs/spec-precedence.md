# Spec Precedence

When artifacts overlap, precedence is:

1. machine-readable contracts and starter files
2. schema and infrastructure specification documents
3. repository and implementation standards
4. requirements and system-level design documents
5. baseline narrative source material

For this repository, canonical executable sources are:

- `docs/contracts/openapi.yaml`
- `docs/contracts/schemas/*.json`
- `alembic/versions/*.py`
- `infra/compose/docker-compose.yml`
- `infra/kubernetes/base/*`
- `infra/tofu/modules/*`
- `infra/tofu/environments/*`
