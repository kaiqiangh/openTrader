package bridge

import (
	"errors"
	"fmt"
	"strings"
)

type Operation string

const (
	OperationCreateOrder Operation = "CREATE_ORDER"
	OperationCancelOrder Operation = "CANCEL_ORDER"
)

type Action string

const (
	ActionBuy    Action = "BUY"
	ActionSell   Action = "SELL"
	ActionClose  Action = "CLOSE"
	ActionCancel Action = "CANCEL"
)

type Command struct {
	CommandID       string    `json:"command_id"`
	Operation       Operation `json:"operation"`
	Action          Action    `json:"action"`
	Symbol          string    `json:"symbol"`
	Quantity        float64   `json:"quantity"`
	ReduceOnly      bool      `json:"reduce_only"`
	IdempotencyKey  string    `json:"idempotency_key"`
	ClientOrderID   string    `json:"client_order_id,omitempty"`
	ExchangeOrderID string    `json:"exchange_order_id,omitempty"`
	TraceID         string    `json:"trace_id"`
	DecisionID      string    `json:"decision_id"`
}

type Result struct {
	OrderID     string         `json:"order_id"`
	Status      string         `json:"status"`
	RawResponse map[string]any `json:"raw_response"`
}

type Client interface {
	Execute(command Command) (Result, error)
}

func (c Command) Validate() error {
	if strings.TrimSpace(c.CommandID) == "" {
		return errors.New("command_id is required")
	}
	if strings.TrimSpace(c.IdempotencyKey) == "" {
		return errors.New("idempotency_key is required")
	}
	if strings.TrimSpace(c.Symbol) == "" {
		return errors.New("symbol is required")
	}
	if strings.TrimSpace(c.TraceID) == "" {
		return errors.New("trace_id is required")
	}
	if strings.TrimSpace(c.DecisionID) == "" {
		return errors.New("decision_id is required")
	}

	switch c.Operation {
	case OperationCreateOrder:
		switch c.Action {
		case ActionBuy, ActionSell, ActionClose:
		default:
			return fmt.Errorf("invalid action for create operation: %s", c.Action)
		}
		if c.Quantity <= 0 {
			return errors.New("quantity must be positive for create operation")
		}
	case OperationCancelOrder:
		if c.Action != ActionCancel {
			return errors.New("cancel operation requires action CANCEL")
		}
		if strings.TrimSpace(c.ExchangeOrderID) == "" && strings.TrimSpace(c.ClientOrderID) == "" {
			return errors.New("cancel operation requires exchange_order_id or client_order_id")
		}
	default:
		return fmt.Errorf("unsupported operation: %s", c.Operation)
	}

	return nil
}

func NewCreateOrderCommand(commandID string, idempotencyKey string, action Action, symbol string, quantity float64, traceID string, decisionID string, clientOrderID string) Command {
	reduceOnly := action == ActionClose
	return Command{
		CommandID:      commandID,
		Operation:      OperationCreateOrder,
		Action:         action,
		Symbol:         symbol,
		Quantity:       quantity,
		ReduceOnly:     reduceOnly,
		IdempotencyKey: idempotencyKey,
		ClientOrderID:  clientOrderID,
		TraceID:        traceID,
		DecisionID:     decisionID,
	}
}

func NewCancelOrderCommand(commandID string, idempotencyKey string, symbol string, exchangeOrderID string, clientOrderID string, traceID string, decisionID string) Command {
	return Command{
		CommandID:       commandID,
		Operation:       OperationCancelOrder,
		Action:          ActionCancel,
		Symbol:          symbol,
		Quantity:        0,
		IdempotencyKey:  idempotencyKey,
		ExchangeOrderID: exchangeOrderID,
		ClientOrderID:   clientOrderID,
		TraceID:         traceID,
		DecisionID:      decisionID,
	}
}
