package main

import (
	"context"
	"fmt"
	"log"
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

	store := resolveIdempotencyStore()
	bridgeClient := bridge.NewHTTPBridgeClientFromEnv()
	queueConsumer := consumer.NewRabbitMQHTTPConsumerFromEnv()
	eventPublisher := publisher.NewRabbitMQHTTPPublisherFromEnv()
	handler, err := service.NewHandler(bridgeClient, store, eventPublisher)
	if err != nil {
		fmt.Fprintf(os.Stderr, "handler init failed: %v\n", err)
		os.Exit(1)
	}
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

func resolveIdempotencyStore() idempotency.Store {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379/0"
	}
	redisStore, err := idempotency.NewRedisStore(redisURL)
	if err == nil {
		log.Printf("idempotency: using Redis store")
		return redisStore
	}
	log.Printf("idempotency: Redis unavailable (%v), falling back to in-memory", err)
	return idempotency.NewInMemoryStore()
}
