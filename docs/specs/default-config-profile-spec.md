# Default Configuration Profile Specification

## Purpose

This document defines the baseline configuration expectations that allow the system to run with minimal tuning.

## Default Profile

The default profile should assume:

- one local provider
- one or two frontier providers
- request logging enabled
- candidate capture disabled by default unless explicitly enabled
- conservative timeouts
- conservative request limits
- local-only privacy mode available

## Goal

An operator should be able to start the system with safe defaults and add complexity later rather than tuning every subsystem immediately.
