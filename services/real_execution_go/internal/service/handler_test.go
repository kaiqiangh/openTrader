package service

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"open-trader/real_execution_go/internal/bridge"
	"open-trader/real_execution_go/internal/idempotency"
)

type fakeBridge struct {
	calls []bridge.Command
	err   error
}

func (f *fakeBridge) Execute(command bridge.Command) (bridge.Result, error) {
	f.calls = append(f.calls, command)
	if f.err != nil {
		return bridge.Result{}, f.err
	}
	return bridge.Result{OrderID: "order-1", Status: "submitted"}, nil
}

type fakePublisher struct {
	routingKeys []string
	envelopes   []map[string]any
	err         error
}

func (f *fakePublisher) Publish(ctx context.Context, routingKey string, message map[string]any) error {
	_ = ctx
	f.routingKeys = append(f.routingKeys, routingKey)
	f.envelopes = append(f.envelopes, message)
	return f.err
}

func realEnvelope(t *testing.T, action string, idempotencyKey string) []byte {
	t.Helper()
	payload := map[string]any{
		"trace_id":        "trace-1",
		"decision_id":     "decision-1",
		"mode":            "REAL",
		"idempotency_key": idempotencyKey,
		"event_type":      "execution.intent.created",
		"emitted_at":      "2026-02-14T00:00:00Z",
		"payload": map[string]any{
			"strategy_id": "scalp-long-short",
			"symbol":      "BTC/USDT",
			"action":      action,
			"quantity":    0.2,
		},
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal envelope: %v", err)
	}
	return encoded
}

func TestHandlerDispatchesCreateIntent(t *testing.T) {
	bridgeClient := &fakeBridge{}
	store := idempotency.NewInMemoryStore()
	handler := NewHandler(bridgeClient, store)

	err := handler.Handle(context.Background(), realEnvelope(t, "BUY", "idem-1"))
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(bridgeClient.calls) != 1 {
		t.Fatalf("expected one bridge call, got %d", len(bridgeClient.calls))
	}
	if bridgeClient.calls[0].Operation != bridge.OperationCreateOrder {
		t.Fatalf("expected create operation, got %s", bridgeClient.calls[0].Operation)
	}
}

func TestHandlerDedupesDuplicateCreateIntent(t *testing.T) {
	bridgeClient := &fakeBridge{}
	store := idempotency.NewInMemoryStore()
	handler := NewHandler(bridgeClient, store)

	body := realEnvelope(t, "SELL", "idem-dup")
	if err := handler.Handle(context.Background(), body); err != nil {
		t.Fatalf("first handle failed: %v", err)
	}
	if err := handler.Handle(context.Background(), body); err != nil {
		t.Fatalf("second handle failed unexpectedly: %v", err)
	}
	if len(bridgeClient.calls) != 1 {
		t.Fatalf("expected deduped bridge calls = 1, got %d", len(bridgeClient.calls))
	}
}

func TestHandlerDispatchesCancelIntent(t *testing.T) {
	bridgeClient := &fakeBridge{}
	store := idempotency.NewInMemoryStore()
	handler := NewHandler(bridgeClient, store)

	payload := map[string]any{
		"trace_id":        "trace-1",
		"decision_id":     "decision-1",
		"mode":            "REAL",
		"idempotency_key": "idem-cancel",
		"event_type":      "execution.intent.created",
		"emitted_at":      "2026-02-14T00:00:00Z",
		"payload": map[string]any{
			"strategy_id":       "scalp-long-short",
			"symbol":            "BTC/USDT",
			"action":            "CANCEL",
			"quantity":          0.0,
			"exchange_order_id": "order-raw-1",
		},
	}
	body, _ := json.Marshal(payload)

	err := handler.Handle(context.Background(), body)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(bridgeClient.calls) != 1 {
		t.Fatalf("expected one bridge call, got %d", len(bridgeClient.calls))
	}
	if bridgeClient.calls[0].Operation != bridge.OperationCancelOrder {
		t.Fatalf("expected cancel operation, got %s", bridgeClient.calls[0].Operation)
	}
}

func TestHandlerRejectsNonRealMode(t *testing.T) {
	bridgeClient := &fakeBridge{}
	store := idempotency.NewInMemoryStore()
	handler := NewHandler(bridgeClient, store)

	payload := map[string]any{
		"trace_id":        "trace-1",
		"decision_id":     "decision-1",
		"mode":            "MOCK",
		"idempotency_key": "idem-1",
		"event_type":      "execution.intent.created",
		"emitted_at":      "2026-02-14T00:00:00Z",
		"payload": map[string]any{
			"strategy_id": "scalp-long-short",
			"symbol":      "BTC/USDT",
			"action":      "BUY",
			"quantity":    0.2,
		},
	}
	body, _ := json.Marshal(payload)

	if err := handler.Handle(context.Background(), body); err == nil {
		t.Fatal("expected non-real mode to be rejected")
	}
	if len(bridgeClient.calls) != 0 {
		t.Fatalf("expected zero bridge calls, got %d", len(bridgeClient.calls))
	}
}

func TestHandlerMarksFailureWhenBridgeFails(t *testing.T) {
	bridgeClient := &fakeBridge{err: errors.New("bridge down")}
	store := idempotency.NewInMemoryStore()
	handler := NewHandler(bridgeClient, store)

	body := realEnvelope(t, "BUY", "idem-fail")
	if err := handler.Handle(context.Background(), body); err == nil {
		t.Fatal("expected bridge error")
	}
	record, exists := store.Get("idem-fail:CREATE_ORDER")
	if !exists {
		t.Fatal("expected failure record")
	}
	if record.Status != idempotency.StatusFailed {
		t.Fatalf("expected failed status, got %s", record.Status)
	}
}

func TestHandlerPublishesSubmittedEventOnSuccess(t *testing.T) {
	bridgeClient := &fakeBridge{}
	store := idempotency.NewInMemoryStore()
	eventPublisher := &fakePublisher{}
	handler := NewHandler(bridgeClient, store, eventPublisher)

	err := handler.Handle(context.Background(), realEnvelope(t, "BUY", "idem-publish-success"))
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(eventPublisher.routingKeys) != 1 {
		t.Fatalf("expected one lifecycle event, got %d", len(eventPublisher.routingKeys))
	}
	if eventPublisher.routingKeys[0] != "oms.order.submitted" {
		t.Fatalf("expected oms.order.submitted, got %s", eventPublisher.routingKeys[0])
	}
}

func TestHandlerPublishesRejectedEventWhenBridgeFails(t *testing.T) {
	bridgeClient := &fakeBridge{err: errors.New("bridge down")}
	store := idempotency.NewInMemoryStore()
	eventPublisher := &fakePublisher{}
	handler := NewHandler(bridgeClient, store, eventPublisher)

	err := handler.Handle(context.Background(), realEnvelope(t, "SELL", "idem-publish-fail"))
	if err == nil {
		t.Fatal("expected bridge failure")
	}
	if len(eventPublisher.routingKeys) != 1 {
		t.Fatalf("expected one lifecycle event, got %d", len(eventPublisher.routingKeys))
	}
	if eventPublisher.routingKeys[0] != "oms.order.rejected" {
		t.Fatalf("expected oms.order.rejected, got %s", eventPublisher.routingKeys[0])
	}
}
