# Security Control Matrix

| Security Control | Primary Spec | Code/Artifact Location | Verification Expectation |
|---|---|---|---|
| authenticated API access | `authn-authz-spec.md` | `app/api/` | integration test |
| privileged endpoint authorization | `authn-authz-spec.md` | `app/api/` | integration + security test |
| secret externalization | `security-operations-spec.md` | config/runtime/infra | config review + deployment check |
| secret rotation support | `secret-rotation-and-key-management-spec.md` | runtime + ops | operational review |
| audit logging for privileged actions | `security-operations-spec.md` | app/integration/services | integration test |
| restricted-data remote-routing prevention | `data-governance-spec.md` + `threat-model.md` | routing logic | unit + integration test |
| blocked/secret export prevention | `data-governance-spec.md` | dataset/export path | unit + integration test |
| private data services | `security-operations-spec.md` | infra manifests/IaC | deployment review |
| TLS in production | `security-operations-spec.md` | ingress/deployment | release verification |
| supply-chain integrity checks | `supply-chain-security-spec.md` | CI/CD pipeline | CI/release gate |
