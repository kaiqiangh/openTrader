package idempotency

import "testing"

func TestStoreDedupesDispatchKey(t *testing.T) {
	store := NewInMemoryStore()

	if ok := store.TryStart("k1"); !ok {
		t.Fatal("expected first TryStart to succeed")
	}
	if ok := store.TryStart("k1"); ok {
		t.Fatal("expected duplicate TryStart to be rejected")
	}

	store.MarkCompleted("k1", "order-1")
	record, exists := store.Get("k1")
	if !exists {
		t.Fatal("expected record to exist")
	}
	if record.Status != StatusCompleted {
		t.Fatalf("expected completed status, got %s", record.Status)
	}
	if record.OrderID != "order-1" {
		t.Fatalf("expected order id order-1, got %s", record.OrderID)
	}
}
