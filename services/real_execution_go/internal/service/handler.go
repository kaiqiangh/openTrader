package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"open-trader/real_execution_go/internal/bridge"
	"open-trader/real_execution_go/internal/idempotency"
)

var ErrUnsupportedAction = errors.New("unsupported action")

type Handler struct {
	Bridge bridge.Client
	Store  idempotency.Store
	Now    func() time.Time
}

func NewHandler(bridgeClient bridge.Client, store idempotency.Store) *Handler {
	return &Handler{
		Bridge: bridgeClient,
		Store:  store,
		Now:    time.Now,
	}
}

func (h *Handler) Handle(ctx context.Context, body []byte) error {
	_ = ctx
	envelope, err := DecodeEnvelope(body)
	if err != nil {
		return err
	}

	command, dispatchKey, err := h.toBridgeCommand(envelope)
	if err != nil {
		return err
	}

	if !h.Store.TryStart(dispatchKey) {
		return nil
	}

	result, err := h.Bridge.Execute(command)
	if err != nil {
		h.Store.MarkFailed(dispatchKey, err.Error())
		return fmt.Errorf("bridge execute failed: %w", err)
	}
	h.Store.MarkCompleted(dispatchKey, result.OrderID)
	return nil
}

func (h *Handler) toBridgeCommand(envelope Envelope) (bridge.Command, string, error) {
	action := strings.ToUpper(strings.TrimSpace(envelope.Payload.Action))
	commandID := fmt.Sprintf("cmd-%s", envelope.DecisionID)

	switch action {
	case string(bridge.ActionBuy), string(bridge.ActionSell), string(bridge.ActionClose):
		quantity := envelope.Payload.Quantity
		if quantity <= 0 {
			quantity = -quantity
		}
		cmd := bridge.NewCreateOrderCommand(
			commandID,
			envelope.IdempotencyKey,
			bridge.Action(action),
			envelope.Payload.Symbol,
			quantity,
			envelope.TraceID,
			envelope.DecisionID,
			envelope.Payload.ClientOrderID,
		)
		if err := cmd.Validate(); err != nil {
			return bridge.Command{}, "", err
		}
		dispatchKey := fmt.Sprintf("%s:%s", envelope.IdempotencyKey, cmd.Operation)
		return cmd, dispatchKey, nil
	case string(bridge.ActionCancel):
		cmd := bridge.NewCancelOrderCommand(
			commandID,
			envelope.IdempotencyKey,
			envelope.Payload.Symbol,
			envelope.Payload.ExchangeOrderID,
			envelope.Payload.ClientOrderID,
			envelope.TraceID,
			envelope.DecisionID,
		)
		if err := cmd.Validate(); err != nil {
			return bridge.Command{}, "", err
		}
		dispatchKey := fmt.Sprintf("%s:%s", envelope.IdempotencyKey, cmd.Operation)
		return cmd, dispatchKey, nil
	default:
		return bridge.Command{}, "", fmt.Errorf("%w: %s", ErrUnsupportedAction, action)
	}
}
