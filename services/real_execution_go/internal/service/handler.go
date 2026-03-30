package service

import (
	"context"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"

	"open-trader/real_execution_go/internal/bridge"
	"open-trader/real_execution_go/internal/idempotency"
	"open-trader/real_execution_go/internal/publisher"
)

var ErrUnsupportedAction = errors.New("unsupported action")

type Handler struct {
	Bridge    bridge.Client
	Store     idempotency.Store
	Publisher publisher.MessagePublisher
	Now       func() time.Time
}

func NewHandler(
	bridgeClient bridge.Client,
	store idempotency.Store,
	eventPublisher ...publisher.MessagePublisher,
) (*Handler, error) {
	if bridgeClient == nil {
		return nil, errors.New("bridge client is required")
	}
	if store == nil {
		return nil, errors.New("idempotency store is required")
	}
	var configuredPublisher publisher.MessagePublisher
	if len(eventPublisher) > 0 {
		configuredPublisher = eventPublisher[0]
	}
	return &Handler{
		Bridge:    bridgeClient,
		Store:     store,
		Publisher: configuredPublisher,
		Now:       time.Now,
	}, nil
}

func (h *Handler) Handle(ctx context.Context, body []byte) error {
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
		if publishErr := h.publishLifecycleEvent(ctx, envelope, command, bridge.Result{}, err); publishErr != nil {
			return fmt.Errorf("bridge execute failed: %w; publish failed: %v", err, publishErr)
		}
		return fmt.Errorf("bridge execute failed: %w", err)
	}
	h.Store.MarkCompleted(dispatchKey, result.OrderID)
	if publishErr := h.publishLifecycleEvent(ctx, envelope, command, result, nil); publishErr != nil {
		return fmt.Errorf("publish lifecycle event failed: %w", publishErr)
	}
	return nil
}

func (h *Handler) toBridgeCommand(envelope Envelope) (bridge.Command, string, error) {
	action := strings.ToUpper(strings.TrimSpace(envelope.Payload.Action))
	commandID := fmt.Sprintf("cmd-%s", envelope.DecisionID)
	orderType := bridge.OrderType(strings.ToUpper(strings.TrimSpace(envelope.Payload.OrderType)))
	if orderType == "" {
		orderType = bridge.OrderTypeMarket
	}
	timeInForce := strings.ToUpper(strings.TrimSpace(envelope.Payload.TimeInForce))
	reduceOnly := envelope.Payload.ReduceOnly

	switch action {
	case string(bridge.ActionBuy), string(bridge.ActionSell), string(bridge.ActionClose):
		quantity := math.Abs(envelope.Payload.Quantity)
		if quantity == 0 {
			return bridge.Command{}, "", fmt.Errorf("quantity must be non-zero for %s action", action)
		}
		if action == string(bridge.ActionClose) {
			reduceOnly = true
		}
		cmd := bridge.NewCreateOrderCommand(
			commandID,
			envelope.IdempotencyKey,
			bridge.Action(action),
			envelope.Payload.Exchange,
			envelope.Payload.Symbol,
			quantity,
			envelope.TraceID,
			envelope.DecisionID,
			envelope.Payload.ClientOrderID,
			orderType,
			timeInForce,
			envelope.Payload.LimitPrice,
			envelope.Payload.TriggerPrice,
			reduceOnly,
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
			envelope.Payload.Exchange,
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

func (h *Handler) publishLifecycleEvent(
	ctx context.Context,
	envelope Envelope,
	command bridge.Command,
	result bridge.Result,
	bridgeErr error,
) error {
	if h.Publisher == nil {
		return nil
	}
	emittedAt := h.Now().UTC().Format(time.RFC3339Nano)
	status := strings.ToUpper(strings.TrimSpace(result.Status))
	eventType := "oms.order.submitted"
	if bridgeErr != nil {
		eventType = "oms.order.rejected"
		status = "REJECTED"
	} else {
		switch status {
		case "FILLED":
			eventType = "oms.order.filled"
		case "PARTIALLY_FILLED":
			eventType = "oms.order.partially_filled"
		case "CANCELLED", "CANCELED":
			eventType = "oms.order.canceled"
		case "REJECTED":
			eventType = "oms.order.rejected"
		default:
			status = "SUBMITTED"
		}
	}

	orderID := firstNonEmpty(
		strings.TrimSpace(result.OrderID),
		strings.TrimSpace(command.ExchangeOrderID),
		strings.TrimSpace(command.ClientOrderID),
		fmt.Sprintf("order-%s", envelope.DecisionID),
	)
	quantity := math.Abs(command.Quantity)
	eventPayload := map[string]any{
		"strategy_id":       envelope.Payload.StrategyID,
		"order_id":          orderID,
		"exchange_order_id": firstNonEmpty(strings.TrimSpace(result.OrderID), strings.TrimSpace(command.ExchangeOrderID)),
		"client_order_id":   command.ClientOrderID,
		"exchange":          command.Exchange,
		"symbol":            command.Symbol,
		"mode":              "REAL",
		"action":            string(command.Action),
		"order_type":        string(command.OrderType),
		"time_in_force":     command.TimeInForce,
		"limit_price":       command.LimitPrice,
		"trigger_price":     command.TriggerPrice,
		"reduce_only":       command.ReduceOnly,
		"quantity":          quantity,
		"status":            status,
	}
	if bridgeErr != nil {
		eventPayload["error"] = bridgeErr.Error()
	}

	eventEnvelope := map[string]any{
		"trace_id":        envelope.TraceID,
		"decision_id":     envelope.DecisionID,
		"mode":            "REAL",
		"idempotency_key": fmt.Sprintf("%s:%s", eventType, envelope.IdempotencyKey),
		"event_type":      eventType,
		"emitted_at":      emittedAt,
		"payload":         eventPayload,
		"service":         "real_execution_go",
	}
	return h.Publisher.Publish(ctx, eventType, eventEnvelope)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			return trimmed
		}
	}
	return ""
}
