package main

import (
	"context"
	"errors"
	"fmt"
	"time"

	"open-trader/real_execution_go/internal/bridge"
	"open-trader/real_execution_go/internal/consumer"
	"open-trader/real_execution_go/internal/idempotency"
	"open-trader/real_execution_go/internal/metrics"
	"open-trader/real_execution_go/internal/service"
)

type noopConsumer struct{}

func (c *noopConsumer) Receive(ctx context.Context, queue string) (consumer.Delivery, error) {
	_ = ctx
	_ = queue
	return consumer.Delivery{}, consumer.ErrNoMessage
}

type noopBridge struct{}

func (b *noopBridge) Execute(command bridge.Command) (bridge.Result, error) {
	_ = command
	return bridge.Result{}, errors.New("bridge client not configured")
}

func main() {
	store := idempotency.NewInMemoryStore()
	handler := service.NewHandler(&noopBridge{}, store)
	runner := &service.Runner{
		QueueName: "execution.intent.real",
		Consumer:  &noopConsumer{},
		Handler:   handler,
		Metrics:   metrics.NewCollector(),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	_ = runner.Run(ctx)

	fmt.Println("real_execution_go queue consumer skeleton ready")
}
