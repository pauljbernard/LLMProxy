# Critical Path Test Matrix

| Path | Unit | Integration | E2E | Security | Release Gate |
|---|---|---|---|---|---|
| chat endpoint | required | required | required | optional | yes |
| routing decision persistence | required | required | optional | optional | yes |
| provider fallback | required | required | optional | optional | yes |
| candidate export gating | required | required | optional | required | yes |
| dataset import validation | required | required | optional | optional | yes |
| promotion gate | required | required | optional | optional | yes |
| rollback execution | required | required | required | optional | yes |
| privileged endpoint authz | optional | required | optional | required | yes |
| secret redaction | required | required | optional | required | yes |
| migration compatibility | optional | required | optional | optional | yes |
