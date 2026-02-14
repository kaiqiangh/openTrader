# ADR-0001: Architecture Baseline

## Status
Accepted

## Context
This repository follows `docs/ARD_Consolidated.md` as architecture source of truth.

## Decision
Adopt Python 3.13+, Go for performance-critical execution services, RabbitMQ, Redis, PostgreSQL + TimescaleDB, Docker Compose, and `.env`-based configuration.

## Consequences
All future implementation tasks must conform to this stack unless superseded by a new ADR.
