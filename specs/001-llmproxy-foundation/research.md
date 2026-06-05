# Research Notes: llmProxy Foundation

## Key Decisions

- Python/FastAPI is preferred for v1 due to ecosystem fit
- Postgres is the system of record
- Redis is the queue/cache substrate
- local specialists use LoRA/QLoRA adaptation rather than frontier-scale training
- local, AWS, GCP, and Azure are first-class deployment targets

## Strategic Rationale

- shift repeatable narrow-domain token use from frontier inference to local specialists
- preserve cost visibility and promotion discipline
- preserve auditability and rollback

## Reference Library

- `docs/specs/economics-and-kpis.md`
- `docs/specs/provider-strategy.md`
- `docs/specs/domain-specialization-plan.md`
