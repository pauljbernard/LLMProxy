# Security Incident Response Specification

## Purpose

This document defines the minimum response expectations for security-relevant incidents.

## Security Incident Classes

- `SEC1`: active credential compromise, broad data exposure, or privilege bypass
- `SEC2`: suspected restricted-data leak, major policy bypass, or supply-chain concern
- `SEC3`: localized security defect without confirmed exploitation

## Initial Response Actions

### Credential Compromise

1. revoke or rotate affected credentials
2. assess blast radius
3. review audit logs
4. restrict affected provider or service path if needed

### Restricted Data Exposure

1. stop further export or routing of affected class
2. identify affected records, packages, or sessions
3. preserve audit evidence
4. apply purge or containment actions where appropriate

### Unauthorized Privileged Action

1. identify acting identity
2. halt further privileged use if necessary
3. review deployment and routing changes
4. rollback if production state was altered

## Evidence Preservation

Security response should preserve:

- audit logs
- routing decision records
- export records
- deployment records
- CI/CD metadata if release-path compromise is suspected

## Recovery Expectation

Security response is not complete until:

- affected credentials are rotated if needed
- unsafe routes or deployments are contained
- affected exports or packages are reviewed
- follow-up remediation is documented
