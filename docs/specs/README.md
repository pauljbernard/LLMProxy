# LLM Proxy Specification Reference Library

This project is being run as a SpecKit-inspired, spec-driven development effort.

The documents in this directory are the extended reference artifacts that elaborate the custom SpecKit-aligned core workflow artifacts under `specs/` and `.specify/`.

## Document Set

- `constitution.md`: project principles, operating constraints, and non-negotiable quality bars
- `requirements.md`: functional and non-functional requirements
- `system-specification.md`: architecture, core components, workflows, and repository structure
- `data-contracts.md`: API, dataset, event, and deployment contract definitions
- `provider-strategy.md`: required frontier provider coverage, fallback policy, and provider capability expectations
- `routing-policy-spec.md`: session-aware model selection rules, ranking inputs, and routing decision behavior
- `economics-and-kpis.md`: measurable cost, performance, and learning-loop success metrics
- `metrics-spec.md`: canonical KPI formulas, event sources, and reporting rules
- `domain-specialization-plan.md`: initial specialization domains, benchmark strategy, and promotion criteria for local specialists
- `glossary.md`: canonical terminology used across the specification set
- `repository-standard.md`: mandatory repository layout, module boundaries, and naming rules
- `implementation-charter.md`: anti-improvisation execution rules for coding agents
- `api-schema-spec.md`: canonical API request/response shapes for the first implementation
- `database-schema-spec.md`: canonical first-pass database entities and required columns
- `deployment-architecture.md`: reference topologies for local, AWS, GCP, and Azure deployments
- `runtime-environment-spec.md`: required services, ports, storage, and environment variables
- `container-and-release-standard.md`: build, packaging, release, migration, and rollback rules
- `cloud-operations-runbook.md`: production observability, backup, alerting, and incident guidance
- `security-operations-spec.md`: secret management, IAM, TLS, audit, and production security rules
- `infrastructure-mapping.md`: logical-to-physical service mappings across local, AWS, GCP, and Azure
- `iac-standard.md`: canonical OpenTofu, Kubernetes, and Compose infrastructure layout
- `deployment-manifest-standard.md`: mandatory manifest structure and mutation rules
- `kubernetes-base-spec.md`: base workload, service, autoscaling, and security expectations
- `compose-spec.md`: canonical local Compose deployment standard
- `opentofu-module-spec.md`: required module and environment entrypoint structure
- `cloud-terraform-mapping.md`: provider-specific OpenTofu resource mapping guidance
- `engineering-workflow-standard.md`: branching, PR, review, and release-approval workflow rules
- `test-strategy.md`: testing responsibilities, gates, and critical-path coverage expectations
- `ci-cd-spec.md`: canonical CI and release pipeline behavior
- `data-governance-spec.md`: retention, privacy, export, and governance rules
- `versioning-and-deprecation-policy.md`: lifecycle rules for APIs, schemas, policies, and modules
- `model-package-spec.md`: canonical portable packaging for local specialists and adapters
- `asset-provenance-and-licensing-spec.md`: provenance, ownership, and usage-restriction metadata rules
- `benchmark-artifact-spec.md`: portable benchmark artifact format for reproducible evaluation
- `registry-interoperability-spec.md`: future-facing registry metadata contract hook
- `threat-model.md`: trust boundaries, attacker classes, and priority threat categories
- `authn-authz-spec.md`: authenticated access and privileged-operation authorization rules
- `security-incident-response-spec.md`: minimum containment and recovery guidance for security events
- `supply-chain-security-spec.md`: dependency, image, and release integrity expectations
- `secret-rotation-and-key-management-spec.md`: secret lifecycle and rotation expectations
- `build-read-order.md`: mandatory reading order for implementation agents
- `artifact-ownership-matrix.md`: identifies the primary source of truth for each concern
- `performance-slo-spec.md`: initial quantitative performance targets
- `capacity-planning-spec.md`: initial scaling and capacity review triggers
- `phase-1-implementation-checklist.md`: mandatory completion checklist for the first build phase
- `implementation-review-gates.md`: merge blockers and critical-path placeholder rules
- `critical-path-test-matrix.md`: exact test expectations for core system paths
- `security-control-matrix.md`: maps required security controls to code and verification locations
- `deployment-profile-matrix.md`: operating profiles that reduce early complexity
- `operator-playbooks.md`: common operator task flows
- `day-0-day-1-day-2-ops.md`: separates setup, first value, and ongoing operations
- `control-surface-minimization-spec.md`: limits unnecessary v1 operational complexity
- `default-config-profile-spec.md`: safe baseline defaults for early adoption
- `quickstart-paths.md`: staged adoption paths from proxy-only to full loop
- `minimum-viable-adoption-spec.md`: smallest useful deployment definition
- `persona-based-adoption-guide.md`: recommended paths by adopter type
- `prerequisites-matrix.md`: required infra, credentials, and skill by adoption path
- `time-to-first-value-spec.md`: target time-to-value expectations
- `feature-gating-matrix.md`: feature availability by profile
- `coding-agent-iteration-protocol.md`: required iteration behavior and progress reporting
- `implementation-session-template.md`: expected structure for an implementation session
- `progress-report-template.md`: canonical iteration report format
- `clarification-and-decision-log-spec.md`: how clarifications and human decisions are recorded
- `iteration-planning-standard.md`: how work is split into bounded implementation iterations
- `engineer-agent-collaboration-spec.md`: interaction rules between engineer and coding agent
- `branch-lifecycle-spec.md`: branch creation, continuation, merge, and retirement rules
- `pr-management-spec.md`: pull request scope, draft, and merge-management rules
- `multi-session-implementation-spec.md`: how coding-agent work resumes across multiple days
- `spec-precedence.md`: defines which executable and prose artifacts win when they overlap
- `implementation-plan.md`: phased delivery plan, agent build order, and MVP flow
- `acceptance-criteria.md`: exit criteria, promotion gates, and failure handling expectations
- `agent-handoff.md`: execution rules for future coding agents

## Executable Starter Kit

The repository now includes concrete starter artifacts intended to outrank prose where overlap exists:

- `app/`
- `alembic/`
- `docs/contracts/`
- `infra/`
- `pyproject.toml`

## Source of Truth

The initial baseline for this specification set is:

- `/Volumes/data/development/llmProxy/baseline.txt`

If these documents drift from `baseline.txt`, this specification set should be treated as the current working source of truth after explicit review.
