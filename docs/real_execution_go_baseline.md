# Real Execution Go Baseline (P4-004, P4-005, P4-006, P4-007)

This document records the initial Go-side real execution runtime skeleton:

- `services/real_execution_go/internal/consumer/contracts.go`
- `services/real_execution_go/internal/service/runner.go`
- `services/real_execution_go/internal/service/handler.go`
- `services/real_execution_go/internal/service/envelope.go`
- `services/real_execution_go/internal/bridge/contracts.go`
- `services/real_execution_go/internal/idempotency/store.go`
- `services/real_execution_go/internal/metrics/collector.go`
- `services/real_execution_go/main.go`

## Scope

- `P4-004`: queue consumer skeleton for `execution.intent.real`
- `P4-005`: strongly typed Go<->Python bridge contracts for create/cancel execution commands
- `P4-006`: idempotent dispatch and dedupe enforcement keyed by `idempotency_key + operation`
- `P4-007`: real execution runner metrics/tracing counters and latency spans

## Runtime Flow

1. Runner polls configured queue via `consumer.MessageConsumer` interface.
2. Envelope decoder validates `mode=REAL` and `event_type=execution.intent.created`.
3. Handler maps action to bridge command:
- `BUY`/`SELL`/`CLOSE` -> `CREATE_ORDER`
- `CANCEL` -> `CANCEL_ORDER`
4. Idempotency store reserves dispatch key before bridge call.
5. Duplicate dispatch keys are skipped (no second bridge call).
6. On success, dispatch is marked `COMPLETED`; on failure `FAILED`.
7. Runner metrics track loop outcomes (`success`, `failure`, `ack`, `nack`, `no-message`) and latency spans.

## Bridge Contract

`internal/bridge/contracts.go` defines:

- Operation enum: `CREATE_ORDER`, `CANCEL_ORDER`
- Action enum: `BUY`, `SELL`, `CLOSE`, `CANCEL`
- `bridge.Command` with trace, decision, and idempotency metadata
- `bridge.Client` interface for concrete exchange adapter integration

Validation guarantees include:

- required identifiers (`command_id`, `idempotency_key`, `trace_id`, `decision_id`, `symbol`)
- positive quantity for create operations
- cancel operations requiring `exchange_order_id` or `client_order_id`

## Idempotency Model

`internal/idempotency/store.go` implements thread-safe in-memory dedupe:

- `TryStart(dispatchKey)` reserves first execution attempt
- `MarkCompleted` and `MarkFailed` persist terminal status
- repeated key submissions are rejected up-front

Dispatch key format currently used by handler:

- `<idempotency_key>:CREATE_ORDER`
- `<idempotency_key>:CANCEL_ORDER`

## Testing

Go unit tests added:

- `internal/bridge/contracts_test.go`
- `internal/idempotency/store_test.go`
- `internal/metrics/collector_test.go`
- `internal/service/handler_test.go`
- `internal/service/runner_test.go`

Validation command:

```bash
cd services/real_execution_go && GOCACHE=/tmp/go-build go test ./...
```

## Next Step Alignment

With `P4-004`..`P4-007`, `P5-005`..`P5-009`, `P6-001`..`P6-007`, and `P7-001`..`P7-012` now delivered, next work is:

- `P7-013`: Telegram gateway implementation
- `P7-014`: notification preference management APIs
- `P7-015`: notification spam control and retry policy hardening
