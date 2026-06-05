# Minimum Viable Adoption Specification

## Purpose

This document defines the smallest useful deployment of `llmProxy`.

## Minimum Viable Adoption

A minimum viable adoption includes:

- OpenAI-compatible proxy
- one frontier provider adapter
- one local provider adapter or placeholder for future local route
- request and routing logging
- basic auth
- local or cloud deployment through the canonical runtime path

## Why This Matters

The system should provide value before:

- training
- automated evaluation
- promotion automation
- specialist deployment automation

## Success Definition

Minimum adoption is successful when a team can route existing LLM traffic through the proxy, observe behavior, and establish a baseline without committing to the full learning loop.
