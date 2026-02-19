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

type OrderType string

const (
	OrderTypeMarket           OrderType = "MARKET"
	OrderTypeLimit            OrderType = "LIMIT"
	OrderTypeStopMarket       OrderType = "STOP_MARKET"
	OrderTypeTakeProfitMarket OrderType = "TAKE_PROFIT_MARKET"
)

type Command struct {
	CommandID       string    `json:"command_id"`
	Operation       Operation `json:"operation"`
	Action          Action    `json:"action"`
	Exchange        string    `json:"exchange"`
	Symbol          string    `json:"symbol"`
	Quantity        float64   `json:"quantity"`
	OrderType       OrderType `json:"order_type"`
	TimeInForce     string    `json:"time_in_force,omitempty"`
	LimitPrice      *float64  `json:"limit_price,omitempty"`
	TriggerPrice    *float64  `json:"trigger_price,omitempty"`
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
	if strings.TrimSpace(c.Exchange) == "" {
		return errors.New("exchange is required")
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
		orderType := normalizeOrderType(c.OrderType)
		switch orderType {
		case OrderTypeMarket:
			if c.LimitPrice != nil {
				return errors.New("limit_price is not allowed for MARKET orders")
			}
			if c.TriggerPrice != nil {
				return errors.New("trigger_price is not allowed for MARKET orders")
			}
		case OrderTypeLimit:
			if c.LimitPrice == nil || *c.LimitPrice <= 0 {
				return errors.New("limit_price must be positive for LIMIT orders")
			}
			if c.TriggerPrice != nil {
				return errors.New("trigger_price is not allowed for LIMIT orders")
			}
			if strings.TrimSpace(c.TimeInForce) == "" {
				return errors.New("time_in_force is required for LIMIT orders")
			}
		case OrderTypeStopMarket, OrderTypeTakeProfitMarket:
			if c.TriggerPrice == nil || *c.TriggerPrice <= 0 {
				return errors.New("trigger_price must be positive for STOP_MARKET/TAKE_PROFIT_MARKET orders")
			}
			if c.LimitPrice != nil {
				return errors.New("limit_price is not allowed for STOP_MARKET/TAKE_PROFIT_MARKET orders")
			}
		default:
			return fmt.Errorf("unsupported order_type: %s", c.OrderType)
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

func NewCreateOrderCommand(
	commandID string,
	idempotencyKey string,
	action Action,
	exchange string,
	symbol string,
	quantity float64,
	traceID string,
	decisionID string,
	clientOrderID string,
	orderType OrderType,
	timeInForce string,
	limitPrice *float64,
	triggerPrice *float64,
	reduceOnly bool,
) Command {
	resolvedReduceOnly := reduceOnly || action == ActionClose
	return Command{
		CommandID:      commandID,
		Operation:      OperationCreateOrder,
		Action:         action,
		Exchange:       exchange,
		Symbol:         symbol,
		Quantity:       quantity,
		OrderType:      normalizeOrderType(orderType),
		TimeInForce:    strings.TrimSpace(timeInForce),
		LimitPrice:     limitPrice,
		TriggerPrice:   triggerPrice,
		ReduceOnly:     resolvedReduceOnly,
		IdempotencyKey: idempotencyKey,
		ClientOrderID:  clientOrderID,
		TraceID:        traceID,
		DecisionID:     decisionID,
	}
}

func NewCancelOrderCommand(commandID string, idempotencyKey string, exchange string, symbol string, exchangeOrderID string, clientOrderID string, traceID string, decisionID string) Command {
	return Command{
		CommandID:       commandID,
		Operation:       OperationCancelOrder,
		Action:          ActionCancel,
		Exchange:        exchange,
		Symbol:          symbol,
		OrderType:       OrderTypeMarket,
		Quantity:        0,
		IdempotencyKey:  idempotencyKey,
		ExchangeOrderID: exchangeOrderID,
		ClientOrderID:   clientOrderID,
		TraceID:         traceID,
		DecisionID:      decisionID,
	}
}

func normalizeOrderType(orderType OrderType) OrderType {
	normalized := strings.ToUpper(strings.TrimSpace(string(orderType)))
	switch normalized {
	case string(OrderTypeLimit):
		return OrderTypeLimit
	case string(OrderTypeStopMarket):
		return OrderTypeStopMarket
	case string(OrderTypeTakeProfitMarket):
		return OrderTypeTakeProfitMarket
	default:
		return OrderTypeMarket
	}
}
