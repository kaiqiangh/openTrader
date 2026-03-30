# P1 Security & Reliability Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 P1 issues from code review: requested_quantity validation, Go idempotency persistence, per-service secrets isolation, and credential store wiring.

**Architecture:** Each task is independent — different files, different concerns. TDD for all tasks. Python tests via pytest, Go tests via `go test ./...`.

**Tech Stack:** Python 3.13, FastAPI, Go 1.21, Redis, PostgreSQL, Docker Compose, PyJWT, pytest, go test

---

## File Structure

| Task | Files Modified | Files Created |
|------|---------------|---------------|
| SEC-013 | `services/workers/main.py`, `services/workers/execution_lifecycle.py` | `tests/test_requested_quantity_validation.py` |
| CQ-002 | `services/real_execution_go/internal/idempotency/store.go`, `main.go` | `services/real_execution_go/internal/idempotency/redis_store.go`, `services/real_execution_go/internal/idempotency/redis_store_test.go` |
| SEC-015 | `docker-compose.yml` | (none) |
| SEC-004 | `services/api/internal_execution/adapters.py`, `services/shared/runtime/exchange_credentials.py` | (none — deprecation) |

---

## Task 1: SEC-013 — Validate `requested_quantity > 0` at Order Creation

**Context:** `services/workers/main.py:311` creates `requested_quantity = abs(float(payload.get("quantity", 0.0) or 0.0))`. When quantity is 0 or missing, this produces 0. The fill reconciliation engine (`_derive_status`) can't determine FILLED/PARTIALLY_FILLED when `requested_quantity` is 0. This is a data integrity guard — reject bad data early.

**Files:**
- Modify: `services/workers/main.py:308-330`
- Create: `tests/test_requested_quantity_validation.py`

- [ ] **Step 1: Write failing test for zero quantity rejection**

```python
# tests/test_requested_quantity_validation.py
from __future__ import annotations

import pytest


def test_requested_quantity_zero_rejected():
    """Orders with zero requested_quantity should be rejected at creation."""
    from services.workers.main import _resolve_requested_quantity

    with pytest.raises(ValueError, match="requested_quantity must be positive"):
        _resolve_requested_quantity(0.0)


def test_requested_quantity_negative_rejected():
    """Orders with negative requested_quantity should be rejected."""
    from services.workers.main import _resolve_requested_quantity

    with pytest.raises(ValueError, match="requested_quantity must be positive"):
        _resolve_requested_quantity(-1.0)


def test_requested_quantity_none_rejected():
    """Orders with None/missing quantity should be rejected."""
    from services.workers.main import _resolve_requested_quantity

    with pytest.raises(ValueError, match="requested_quantity must be positive"):
        _resolve_requested_quantity(None)


def test_requested_quantity_positive_accepted():
    """Valid positive quantity should return abs value."""
    from services.workers.main import _resolve_requested_quantity

    assert _resolve_requested_quantity(1.5) == 1.5
    assert _resolve_requested_quantity(-2.0) == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_requested_quantity_validation.py -v`
Expected: FAIL with `_resolve_requested_quantity` not defined or no ValueError raised

- [ ] **Step 3: Extract and implement `_resolve_requested_quantity` in `services/workers/main.py`**

In `services/workers/main.py`, find the line:
```python
requested_quantity = abs(float(payload.get("quantity", 0.0) or 0.0))
```

Replace with:
```python
requested_quantity = _resolve_requested_quantity(payload.get("quantity"))
```

Add the function (near top of file, after imports):
```python
def _resolve_requested_quantity(raw_quantity: float | None) -> float:
    """Resolve and validate requested_quantity from raw payload value.

    Raises ValueError if quantity is zero, negative, or missing.
    Returns absolute value (always positive).
    """
    if raw_quantity is None:
        raise ValueError("requested_quantity must be positive (got None)")
    quantity = abs(float(raw_quantity))
    if quantity <= 0:
        raise ValueError(f"requested_quantity must be positive (got {raw_quantity})")
    return quantity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_requested_quantity_validation.py -v`
Expected: PASS

- [ ] **Step 5: Verify no regression**

Run: `.venv/bin/python -m pytest tests/ -x --tb=short`
Expected: 437+ passed (existing tests may need adjustment if they pass zero quantities)

- [ ] **Step 6: Commit**

```bash
git add services/workers/main.py tests/test_requested_quantity_validation.py
git commit -m "fix: validate requested_quantity > 0 at order creation

Extract _resolve_requested_quantity() with explicit ValueError on zero/None.
Prevents orders from being created with undeterminable fill status.

SEC-013"
```

---

## Task 2: CQ-002 — Go Idempotency Store: Redis-Backed

**Context:** Current `InMemoryStore` in `services/real_execution_go/internal/idempotency/store.go` loses state on restart → potential duplicate order submissions. Need Redis-backed implementation with fallback to in-memory.

**Files:**
- Modify: `services/real_execution_go/main.go`
- Create: `services/real_execution_go/internal/idempotency/redis_store.go`
- Create: `services/real_execution_go/internal/idempotency/redis_store_test.go`

- [ ] **Step 1: Write failing test for Redis store**

```go
// services/real_execution_go/internal/idempotency/redis_store_test.go
package idempotency

import (
	"testing"
)

func TestRedisStore_TryStartCreatesRecord(t *testing.T) {
	// Skip if no Redis available
	store, cleanup := newTestRedisStore(t)
	defer cleanup()

	ok := store.TryStart("key-1")
	if !ok {
		t.Fatal("TryStart should return true for new key")
	}

	// Duplicate should be rejected
	ok = store.TryStart("key-1")
	if ok {
		t.Fatal("TryStart should return false for duplicate key")
	}
}

func TestRedisStore_MarkCompletedPersists(t *testing.T) {
	store, cleanup := newTestRedisStore(t)
	defer cleanup()

	store.TryStart("key-2")
	store.MarkCompleted("key-2", "order-123")

	record, found := store.Get("key-2")
	if !found {
		t.Fatal("Get should find completed record")
	}
	if record.Status != StatusCompleted {
		t.Fatalf("expected COMPLETED, got %s", record.Status)
	}
	if record.OrderID != "order-123" {
		t.Fatalf("expected order-123, got %s", record.OrderID)
	}
}

func TestRedisStore_MarkFailedPersists(t *testing.T) {
	store, cleanup := newTestRedisStore(t)
	defer cleanup()

	store.TryStart("key-3")
	store.MarkFailed("key-3", "timeout")

	record, found := store.Get("key-3")
	if !found {
		t.Fatal("Get should find failed record")
	}
	if record.Status != StatusFailed {
		t.Fatalf("expected FAILED, got %s", record.Status)
	}
	if record.LastError != "timeout" {
		t.Fatalf("expected 'timeout', got %s", record.LastError)
	}
}

func TestRedisStore_GetMissingReturnsFalse(t *testing.T) {
	store, cleanup := newTestRedisStore(t)
	defer cleanup()

	_, found := store.Get("nonexistent")
	if found {
		t.Fatal("Get should return false for missing key")
	}
}

func newTestRedisStore(t *testing.T) (*RedisStore, func()) {
	t.Helper()
	// Use REDIS_URL env or default to localhost
	store, err := NewRedisStore(redisURL())
	if err != nil {
		t.Skipf("Redis not available: %v", err)
	}
	cleanup := func() {
		store.Close()
	}
	return store, cleanup
}

func redisURL() string {
	// Default for local testing
	return "redis://localhost:6379/0"
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/real_execution_go && go test ./internal/idempotency/ -v -run TestRedisStore`
Expected: FAIL with `NewRedisStore` undefined

- [ ] **Step 3: Implement `RedisStore`**

```go
// services/real_execution_go/internal/idempotency/redis_store.go
package idempotency

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type RedisStore struct {
	client *redis.Client
	now    func() time.Time
	prefix string
	ttl    time.Duration
}

func NewRedisStore(redisURL string) (*RedisStore, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	client := redis.NewClient(opt)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping: %w", err)
	}

	return &RedisStore{
		client: client,
		now:    time.Now,
		prefix: "idempotency:",
		ttl:    24 * time.Hour,
	}, nil
}

func (s *RedisStore) TryStart(dispatchKey string) bool {
	ctx := context.Background()
	key := s.prefix + dispatchKey

	ok, err := s.client.SetNX(ctx, key, s.marshal(Record{
		DispatchKey: dispatchKey,
		Status:      StatusStarted,
		UpdatedAt:   s.now().UTC(),
	}), s.ttl).Result()
	if err != nil {
		// Redis error — fail open (allow execution) to avoid blocking trades
		return true
	}
	return ok
}

func (s *RedisStore) MarkCompleted(dispatchKey string, orderID string) {
	ctx := context.Background()
	key := s.prefix + dispatchKey

	s.client.Set(ctx, key, s.marshal(Record{
		DispatchKey: dispatchKey,
		Status:      StatusCompleted,
		OrderID:     orderID,
		UpdatedAt:   s.now().UTC(),
	}), s.ttl)
}

func (s *RedisStore) MarkFailed(dispatchKey string, lastError string) {
	ctx := context.Background()
	key := s.prefix + dispatchKey

	s.client.Set(ctx, key, s.marshal(Record{
		DispatchKey: dispatchKey,
		Status:      StatusFailed,
		LastError:   lastError,
		UpdatedAt:   s.now().UTC(),
	}), s.ttl)
}

func (s *RedisStore) Get(dispatchKey string) (Record, bool) {
	ctx := context.Background()
	key := s.prefix + dispatchKey

	data, err := s.client.Get(ctx, key).Bytes()
	if err != nil {
		return Record{}, false
	}

	var record Record
	if err := json.Unmarshal(data, &record); err != nil {
		return Record{}, false
	}
	return record, true
}

func (s *RedisStore) Close() error {
	return s.client.Close()
}

func (s *RedisStore) marshal(record Record) string {
	data, _ := json.Marshal(record)
	return string(data)
}
```

- [ ] **Step 4: Add go-redis dependency**

Run: `cd services/real_execution_go && go get github.com/redis/go-redis/v9`

- [ ] **Step 5: Run test to verify it passes**

Run: `cd services/real_execution_go && go test ./internal/idempotency/ -v -run TestRedisStore`
Expected: PASS (if Redis available) or SKIP (if not)

- [ ] **Step 6: Update `main.go` to use Redis store with fallback**

In `services/real_execution_go/main.go`, find:
```go
store := idempotency.NewInMemoryStore()
```

Replace with:
```go
store := resolveIdempotencyStore()
```

Add function:
```go
func resolveIdempotencyStore() idempotency.Store {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379/0"
	}
	redisStore, err := idempotency.NewRedisStore(redisURL)
	if err == nil {
		log.Printf("idempotency: using Redis store")
		return redisStore
	}
	log.Printf("idempotency: Redis unavailable (%v), falling back to in-memory", err)
	return idempotency.NewInMemoryStore()
}
```

Make sure `os` and `log` are imported.

- [ ] **Step 7: Run all Go tests**

Run: `cd services/real_execution_go && go test ./...`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add services/real_execution_go/
git commit -m "feat: Redis-backed idempotency store with in-memory fallback

New RedisStore persists idempotency state across service restarts,
preventing duplicate order submissions. Falls back to InMemoryStore
when Redis is unavailable.

CQ-002"
```

---

## Task 3: SEC-015 — Per-Service Secrets Isolation

**Context:** Current docker-compose.yml passes all secrets (Telegram token, LLM API key, JWT secret, encryption key, Grafana password, exchange credentials) to every service via inline `environment:` blocks. Violates least-privilege principle. Each service should only receive the secrets it needs.

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Document current secret distribution**

Audit which secrets each service actually needs:

| Service | Needs | Doesn't Need |
|---------|-------|-------------|
| api | JWT_SECRET_KEY, REAL_EXECUTION_BRIDGE_API_KEY, exchange creds (BINANCE/BITGET) | TELEGRAM_BOT_TOKEN, LLM_API_KEY, GRAFANA_ADMIN_PASSWORD |
| notification_worker | TELEGRAM_BOT_TOKEN | JWT_SECRET_KEY, LLM_API_KEY, exchange creds, GRAFANA |
| orchestrator worker | LLM_API_KEY | TELEGRAM_BOT_TOKEN, JWT_SECRET_KEY, exchange creds, GRAFANA |
| execution_lifecycle worker | Exchange creds (BINANCE/BITGET) | TELEGRAM_BOT_TOKEN, LLM_API_KEY, JWT_SECRET_KEY, GRAFANA |
| market worker | None (public APIs) | All secrets |
| oms worker | None | All secrets |
| simulation worker | None | All secrets |
| news worker | None | All secrets |
| grafana | GRAFANA_ADMIN_PASSWORD | Everything else |
| real_execution_go | REAL_EXECUTION_BRIDGE_API_KEY, RabbitMQ creds | Everything else |

- [ ] **Step 2: Remove unnecessary secrets from each service**

For `api` service, remove:
- `TELEGRAM_BOT_TOKEN` (if present — not in current api block, good)
- `LLM_API_KEY` (not in current api block, good)
- `GRAFANA_ADMIN_PASSWORD` (not in current api block, good)

For `notification_worker`, remove:
- All non-notification env vars (already clean — only has Telegram and RabbitMQ)

For `orchestrator worker`, verify only LLM secrets present (already clean).

For `market`, `oms`, `simulation`, `news` workers — verify no secret leakage (they already only have DB + RabbitMQ + non-secret config).

For `grafana` — verify only has GRAFANA creds (already clean).

- [ ] **Step 3: Verify current state is already well-isolated**

After audit, the current docker-compose.yml is actually **already well-isolated**:
- `api` only has JWT, bridge key, exchange creds
- `notification_worker` only has Telegram token
- `orchestrator` only has LLM key
- `execution_lifecycle` only has exchange creds
- Other workers have no secrets

The SEC-015 finding was about `env_file: - .env` which doesn't exist in the current compose file. The inline `environment:` blocks are already per-service filtered.

- [ ] **Step 4: If already isolated, document the finding**

Update the review report to note SEC-015 is already mitigated. No code changes needed.

- [ ] **Step 5: Commit (if any changes) or skip**

If no changes needed:
```bash
git add docs/superpowers/plans/
git commit -m "docs: confirm SEC-015 per-service secrets already isolated

docker-compose.yml uses inline environment blocks per service,
not shared env_file. Each service only receives its required secrets.

SEC-015"
```

If changes are needed (unexpected), commit with appropriate message.

---

## Task 4: SEC-004 — Wire Encrypted Credential Store or Deprecate

**Context:** `EncryptedExchangeCredentialStore` in `services/shared/runtime/exchange_credentials.py` uses SQLite and is never wired at runtime. Exchange adapters read credentials directly from env vars. Need to either: (A) wire the store with PostgreSQL backend, or (B) deprecate the SQLite store and document env vars as the intended boundary.

**Decision:** Option B — deprecate. The env-var approach is standard for Docker deployments, works with Docker secrets, and avoids adding a PostgreSQL credential table that duplicates what `.env` manages. The SQLite store is dead code.

**Files:**
- Delete: `services/shared/runtime/exchange_credentials.py`
- Modify: `services/shared/runtime/__init__.py` (remove export)

- [ ] **Step 1: Verify no runtime imports of `EncryptedExchangeCredentialStore`**

Run: `grep -rn "EncryptedExchangeCredentialStore\|exchange_credentials" services/ --include="*.py" | grep -v "__init__\|exchange_credentials.py"`
Expected: No results (only __init__.py re-export and the file itself)

- [ ] **Step 2: Verify no tests depend on it**

Run: `grep -rn "EncryptedExchangeCredentialStore\|exchange_credentials" tests/ --include="*.py"`
Expected: No results or only import tests

- [ ] **Step 3: Remove the dead code**

Delete `services/shared/runtime/exchange_credentials.py`.

Edit `services/shared/runtime/__init__.py`, remove:
```python
from services.shared.runtime.exchange_credentials import ExchangeCredentials, EncryptedExchangeCredentialStore
```
and remove `"EncryptedExchangeCredentialStore"` and `"ExchangeCredentials"` from `__all__`.

- [ ] **Step 4: Run all tests to verify no breakage**

Run: `.venv/bin/python -m pytest tests/ -x --tb=short`
Expected: PASS (no tests depend on it)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove dead EncryptedExchangeCredentialStore (SQLite)

Never wired at runtime — exchange adapters read credentials from env vars.
SQLite-backed store is dead code. Env var approach is standard for Docker
deployments and works with Docker secrets.

SEC-004"
```

---

## Task 5: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest tests/ -x --tb=short
cd services/real_execution_go && go test ./...
```

- [ ] **Step 2: Verify no regressions**

All tests pass. No new warnings.

- [ ] **Step 3: Summary**

Report all changes made and their corresponding issue IDs.
