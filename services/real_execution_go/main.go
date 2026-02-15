package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"open-trader/real_execution_go/internal/bridge"
	"open-trader/real_execution_go/internal/consumer"
	"open-trader/real_execution_go/internal/idempotency"
	"open-trader/real_execution_go/internal/metrics"
	"open-trader/real_execution_go/internal/publisher"
	"open-trader/real_execution_go/internal/service"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	queueName := strings.TrimSpace(os.Getenv("REAL_EXECUTION_QUEUE_NAME"))
	if queueName == "" {
		queueName = "execution.intent.real"
	}

	store := idempotency.NewInMemoryStore()
	bridgeClient := bridge.NewHTTPBridgeClientFromEnv()
	queueConsumer := consumer.NewRabbitMQHTTPConsumerFromEnv()
	eventPublisher := publisher.NewRabbitMQHTTPPublisherFromEnv()
	handler := service.NewHandler(bridgeClient, store, eventPublisher)
	runner := &service.Runner{
		QueueName: queueName,
		Consumer:  queueConsumer,
		Handler:   handler,
		Metrics:   metrics.NewCollector(),
	}

	fmt.Printf("real_execution_go started (queue=%s)\n", queueName)
	if err := runner.Run(ctx); err != nil {
		fmt.Fprintf(os.Stderr, "real_execution_go stopped with error: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("real_execution_go stopped")
}
