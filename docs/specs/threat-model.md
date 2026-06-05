# Threat Model

## Purpose

This document defines the primary trust boundaries, attacker classes, and high-level threat categories relevant to `llmProxy`.

## Trust Boundaries

The system has these major trust boundaries:

1. external client to ingress
2. ingress to application services
3. application services to data stores
4. application services to frontier providers
5. application services to artifact storage
6. operator actions to privileged control paths

## Primary Assets

The highest-value assets include:

- provider API keys and service credentials
- prompts and responses
- routing decisions
- training candidates and exported datasets
- model packages and promoted local specialists
- deployment and rollback controls

## Attacker Classes

- external unauthenticated caller
- authenticated but unauthorized user
- compromised automation identity
- malicious insider or overprivileged operator
- compromised dependency or container artifact
- remote provider misuse or misrouting exposure

## Key Threat Categories

- secret exposure
- unauthorized API access
- prompt or response data leakage
- export of restricted or secret-bearing training assets
- privilege escalation
- insecure provider routing for restricted data
- tampering with model promotion or rollback state
- supply-chain compromise
- denial of service or resource exhaustion

## High-Priority Abuse Cases

- sending restricted data to remote providers despite privacy policy
- exporting blocked or secret-bearing records into training datasets
- using stolen provider credentials
- manipulating routing policy to bypass safeguards
- registering unauthorized models into production routing
- poisoning benchmark or evaluation inputs to influence promotion

## Required Mitigations

- authenticated ingress
- authorization on privileged endpoints
- audit logging for privileged actions
- least-privilege service identities
- secret externalization
- export gating for sensitive records
- routing-policy enforcement for privacy levels
- rollback and deployment controls
- CI/CD and artifact integrity checks

## Out of Scope

This threat model does not attempt to fully solve:

- nation-state-level hardware compromise
- side-channel attacks on third-party hosted frontier providers
- formal multi-tenant isolation guarantees

These may matter later but are outside the first-version security scope.
