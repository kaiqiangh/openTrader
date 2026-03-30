package idempotency

import (
	"os"
	"testing"
)

func TestRedisStore_TryStartCreatesRecord(t *testing.T) {
	store, cleanup := newTestRedisStore(t)
	defer cleanup()

	ok := store.TryStart("key-1")
	if !ok {
		t.Fatal("TryStart should return true for new key")
	}
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
	url := os.Getenv("REDIS_URL")
	if url == "" {
		url = "redis://localhost:6379/0"
	}
	store, err := NewRedisStore(url)
	if err != nil {
		t.Skipf("Redis not available: %v", err)
	}
	cleanup := func() { store.Close() }
	return store, cleanup
}
