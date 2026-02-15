# Phase 10 Runtime Status + Validation Instincts (2026-02-15)

## Context
- Objective: rebaseline Phase 10 task status using runtime evidence, not contract-only completion.
- Scope: real execution Go service resilience, compose runtime smoke reliability, and plan status alignment.

## Instincts Captured

1. RabbitMQ HTTP 404 race can destabilize consumers
- Signal: `real_execution_go` repeatedly exited on `EOF` while polling missing queue via RabbitMQ management API.
- Action: treat transient consumer errors as recoverable in runtime loop; continue with bounded backoff instead of process exit.
- Confidence: high

2. Host-side smoke probes must normalize container-only endpoints
- Signal: smoke used `RUNTIME_RABBITMQ_HTTP_API_URL` and failed when value resolved to in-network hostnames.
- Action: normalize `rabbitmq` host to `127.0.0.1:15672` for local smoke probes.
- Confidence: high

3. Compose runtime validation must enforce message-flow, not just service-up checks
- Signal: all services reported running while bridge-flow assertion still failed.
- Action: keep explicit publish->consume lifecycle assertion for real-execution to OMS queue path in smoke gate.
- Confidence: high

4. Queue declaration mismatch is common in iterative local runs
- Signal: RabbitMQ `inequivalent arg` errors after partial topology history.
- Action: use tolerant smoke bootstrap helpers for required queues/exchanges/bindings and keep runtime flow assertion authoritative.
- Confidence: medium

5. Phase status should only move to DONE with validated runtime evidence
- Signal: Phase 10 tasks were previously in-progress despite working code paths and green smoke.
- Action: update `IMPLEMENTATION_PLAN.md` statuses after running `make smoke`, targeted pytest, and Go tests.
- Confidence: high

## Follow-up Hooks
- Remove startup-time `uv sync` from runtime containers to reduce DNS/network-induced restart noise in compose.
- Continue P10-003 migration for remaining in-memory/synthetic runtime slices before final Phase 10 closure.
