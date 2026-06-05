# Supply Chain Security Specification

## Purpose

This document defines the minimum integrity expectations for dependencies, images, and release artifacts.

## Scope

Applies to:

- Python dependencies
- container images
- CI/CD release artifacts
- infrastructure manifests

## Required Controls

- dependency locking
- image vulnerability scanning
- manifest validation
- immutable release image tags
- release traceability to commit SHA

## Recommended Additional Controls

- SBOM generation
- artifact signing
- provenance attestation
- periodic dependency review

## Release Integrity Rule

A production release must be traceable to:

- source revision
- CI run
- built image
- migration set

## Dependency Response Rule

Critical dependency vulnerabilities require:

- impact assessment
- remediation plan
- release prioritization based on exposure
