package service

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

type Envelope struct {
	TraceID        string        `json:"trace_id"`
	DecisionID     string        `json:"decision_id"`
	Mode           string        `json:"mode"`
	IdempotencyKey string        `json:"idempotency_key"`
	EventType      string        `json:"event_type"`
	EmittedAt      string        `json:"emitted_at"`
	Payload        IntentPayload `json:"payload"`
}

type IntentPayload struct {
	StrategyID      string  `json:"strategy_id"`
	Symbol          string  `json:"symbol"`
	Action          string  `json:"action"`
	Quantity        float64 `json:"quantity"`
	ClientOrderID   string  `json:"client_order_id,omitempty"`
	ExchangeOrderID string  `json:"exchange_order_id,omitempty"`
}

func DecodeEnvelope(body []byte) (Envelope, error) {
	var envelope Envelope
	if err := json.Unmarshal(body, &envelope); err != nil {
		return Envelope{}, fmt.Errorf("decode envelope: %w", err)
	}
	if err := envelope.Validate(); err != nil {
		return Envelope{}, err
	}
	return envelope, nil
}

func (e Envelope) Validate() error {
	if strings.TrimSpace(e.TraceID) == "" {
		return errors.New("trace_id is required")
	}
	if strings.TrimSpace(e.DecisionID) == "" {
		return errors.New("decision_id is required")
	}
	if strings.ToUpper(strings.TrimSpace(e.Mode)) != "REAL" {
		return fmt.Errorf("real execution service only accepts mode REAL, got %s", e.Mode)
	}
	if strings.TrimSpace(e.IdempotencyKey) == "" {
		return errors.New("idempotency_key is required")
	}
	if strings.TrimSpace(e.EventType) != "execution.intent.created" {
		return fmt.Errorf("unexpected event_type %s", e.EventType)
	}
	if strings.TrimSpace(e.Payload.Symbol) == "" {
		return errors.New("payload.symbol is required")
	}
	if strings.TrimSpace(e.Payload.Action) == "" {
		return errors.New("payload.action is required")
	}
	return nil
}
