package bridge

import "testing"

func TestNewCreateOrderCommandBuildsValidatedContract(t *testing.T) {
	command := NewCreateOrderCommand(
		"cmd-1",
		"idem-1",
		ActionBuy,
		"binance",
		"BTC/USDT",
		0.2,
		"trace-1",
		"decision-1",
		"client-1",
		OrderTypeMarket,
		"",
		nil,
		nil,
		false,
	)

	if command.Operation != OperationCreateOrder {
		t.Fatalf("expected create operation, got %s", command.Operation)
	}
	if err := command.Validate(); err != nil {
		t.Fatalf("expected valid command, got error: %v", err)
	}
}

func TestCancelCommandRequiresOrderIdentifier(t *testing.T) {
	command := NewCancelOrderCommand(
		"cmd-2",
		"idem-2",
		"binance",
		"BTC/USDT",
		"",
		"",
		"trace-2",
		"decision-2",
	)

	if err := command.Validate(); err == nil {
		t.Fatal("expected validation error for missing cancel identifiers")
	}
}
