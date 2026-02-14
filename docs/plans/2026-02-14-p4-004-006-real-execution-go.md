# P4-004 to P4-006 Real Execution Go Skeleton Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the real execution Go skeleton with queue-consumer workflow, Go<->Python bridge contracts, and idempotent dispatch/dedupe logic for create/cancel actions.

**Architecture:** Build a layered Go runtime under `services/real_execution_go/internal` with separate packages for queue consumption, bridge contracts, idempotency store, and command handling. Keep external infrastructure abstract behind interfaces so unit tests can prove behavior without RabbitMQ/exchange dependencies. Wire `main.go` to the new skeleton entrypoint while preserving a safe bootstrap default.

**Tech Stack:** Go 1.21+, stdlib (`context`, `encoding/json`, `sync`, `time`), `go test`.

---

### Task 1: Queue consumer skeleton (`P4-004`)

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/services/real_execution_go/main.go`
- Create: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/consumer/contracts.go`
- Create: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/runner.go`
- Test: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/runner_test.go`

**Step 1: Write the failing test**

```go
func TestRunnerReceivesAndAcksDelivery(t *testing.T) {
    // expect one delivery handled and acked
}
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kai/Desktop/openTrader/services/real_execution_go && go test ./...`
Expected: FAIL because runner/consumer packages do not exist.

**Step 3: Write minimal implementation**

- Add consumer delivery/consumer interfaces.
- Add runner loop that receives delivery and delegates to handler.
- Ensure ack on success and nack on handler error.

**Step 4: Run test to verify it passes**

Run: `cd /Users/kai/Desktop/openTrader/services/real_execution_go && go test ./...`
Expected: PASS for runner behavior.

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/real_execution_go/main.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/consumer/contracts.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/runner.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/runner_test.go
git commit -m "feat(p4-004): add real execution queue consumer runner skeleton"
```

### Task 2: Go<->Python bridge contracts (`P4-005`)

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/bridge/contracts.go`
- Test: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/bridge/contracts_test.go`

**Step 1: Write the failing test**

```go
func TestNewCreateOrderCommandBuildsValidatedContract(t *testing.T) {
    // validates operation/action/quantity fields
}
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kai/Desktop/openTrader/services/real_execution_go && go test ./...`
Expected: FAIL because bridge contract package does not exist.

**Step 3: Write minimal implementation**

- Define strongly typed operation/action enums.
- Define bridge command/result structs and validation.
- Define bridge client interface for command execution.

**Step 4: Run test to verify it passes**

Run: `cd /Users/kai/Desktop/openTrader/services/real_execution_go && go test ./...`
Expected: PASS for bridge contract validations.

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/real_execution_go/internal/bridge/contracts.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/bridge/contracts_test.go
git commit -m "feat(p4-005): add Go-Python execution bridge contracts"
```

### Task 3: Idempotent dispatch and dedupe (`P4-006`)

**Files:**
- Create: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/idempotency/store.go`
- Create: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/handler.go`
- Create: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/envelope.go`
- Test: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/idempotency/store_test.go`
- Test: `/Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/handler_test.go`

**Step 1: Write the failing test**

```go
func TestHandlerDedupesDuplicateCreateIntent(t *testing.T) {
    // second dispatch with same idempotency key must skip bridge call
}
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/kai/Desktop/openTrader/services/real_execution_go && go test ./...`
Expected: FAIL because idempotency and handler modules do not exist.

**Step 3: Write minimal implementation**

- Add thread-safe in-memory idempotency store.
- Parse and validate real-mode execution intent envelope.
- Map actions to create/cancel bridge commands.
- Prevent duplicate dispatch for create/cancel idempotency keys.

**Step 4: Run test to verify it passes**

Run: `cd /Users/kai/Desktop/openTrader/services/real_execution_go && go test ./...`
Expected: PASS for dedupe and command routing behavior.

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/services/real_execution_go/internal/idempotency/store.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/handler.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/envelope.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/idempotency/store_test.go /Users/kai/Desktop/openTrader/services/real_execution_go/internal/service/handler_test.go
git commit -m "feat(p4-006): add idempotent dispatch and dedupe handler"
```

### Task 4: Documentation and plan updates

**Files:**
- Modify: `/Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`
- Modify: `/Users/kai/Desktop/openTrader/README.md`
- Create: `/Users/kai/Desktop/openTrader/docs/real_execution_go_baseline.md`

**Step 1: Write the failing test**

```python
def test_implementation_plan_marks_p4_004_to_p4_006_progress():
    ...
```

**Step 2: Run test to verify it fails**

Run: `rg -n "P4-004|P4-005|P4-006" /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md`
Expected: still `NOT_STARTED` and missing baseline doc references.

**Step 3: Write minimal implementation**

- Update P4 task statuses and turn ledger/update block.
- Add real execution baseline doc with architecture/contracts/flow.
- Update README with file-level references.

**Step 4: Run test to verify it passes**

Run: `rg -n "P4-004|P4-005|P4-006|real_execution_go_baseline" /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/real_execution_go_baseline.md`
Expected: required status and references are present.

**Step 5: Commit**

```bash
git add /Users/kai/Desktop/openTrader/docs/IMPLEMENTATION_PLAN.md /Users/kai/Desktop/openTrader/README.md /Users/kai/Desktop/openTrader/docs/real_execution_go_baseline.md
git commit -m "docs(p4): add real execution baseline and update plan status"
```

## Execution Log (2026-02-14)

- Task 1 status: Completed.
- Task 2 status: Completed.
- Task 3 status: Completed.
- Task 4 status: Completed.
- Notes:
  - User explicitly requested starting `P4-004`, `P4-005`, and `P4-006`.
  - Implementation will stay interface-first and test-driven to keep real exchange integration safely staged.
  - Go module test suite passed for consumer, bridge, idempotency, and handler layers.
