# Quickstart Paths

## Purpose

This document defines adoption paths with increasing complexity.

## Path 1: Proxy Only

Goal:

- expose an OpenAI-compatible endpoint
- route to frontier and local providers
- log requests and routing decisions

## Path 2: Proxy + Capture

Goal:

- everything in `Proxy Only`
- enable candidate capture
- review and export approved examples

## Path 3: Proxy + Capture + Evaluation

Goal:

- everything in `Proxy + Capture`
- run benchmarks
- measure economics and quality

## Path 4: Full Learning Loop

Goal:

- everything in `Proxy + Capture + Evaluation`
- import datasets
- train specialists
- promote and deploy successful specialists

## Rule

Each path should be independently useful. Later paths must build on earlier ones rather than replacing them.
