package service

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"open-trader/real_execution_go/internal/consumer"
	"open-trader/real_execution_go/internal/metrics"
)

type BodyHandler interface {
	Handle(ctx context.Context, body []byte) error
}

type Runner struct {
	QueueName string
	Consumer  consumer.MessageConsumer
	Handler   BodyHandler
	Metrics   *metrics.Collector
}

func (r *Runner) Run(ctx context.Context) error {
	if r.QueueName == "" {
		return errors.New("queue name is required")
	}
	if r.Consumer == nil {
		return errors.New("consumer is required")
	}
	if r.Handler == nil {
		return errors.New("handler is required")
	}

	for {
		if err := ctx.Err(); err != nil {
			return nil
		}

		delivery, err := r.Consumer.Receive(ctx, r.QueueName)
		if err != nil {
			if errors.Is(err, consumer.ErrNoMessage) {
				if r.Metrics != nil {
					r.Metrics.RecordNoMessage(r.QueueName)
				}
				continue
			}
			if r.Metrics != nil {
				r.Metrics.RecordRunFailure(r.QueueName, 0, "consumer_error", "", "")
			}
			return err
		}

		started := time.Now()
		traceID, decisionID := extractTraceMetadata(delivery.Body)
		handleErr := r.Handler.Handle(ctx, delivery.Body)
		if handleErr != nil {
			if delivery.Nack != nil {
				_ = delivery.Nack(true)
				if r.Metrics != nil {
					r.Metrics.RecordNack(r.QueueName)
				}
			}
			if r.Metrics != nil {
				r.Metrics.RecordRunFailure(r.QueueName, time.Since(started), "handler_error", traceID, decisionID)
			}
			continue
		}
		if delivery.Ack != nil {
			if ackErr := delivery.Ack(); ackErr != nil {
				if r.Metrics != nil {
					r.Metrics.RecordRunFailure(r.QueueName, time.Since(started), "ack_error", traceID, decisionID)
				}
				return ackErr
			}
			if r.Metrics != nil {
				r.Metrics.RecordAck(r.QueueName)
			}
		}
		if r.Metrics != nil {
			r.Metrics.RecordRunSuccess(r.QueueName, time.Since(started), traceID, decisionID)
		}
	}
}

func extractTraceMetadata(body []byte) (string, string) {
	var envelope struct {
		TraceID    string `json:"trace_id"`
		DecisionID string `json:"decision_id"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return "", ""
	}
	return strings.TrimSpace(envelope.TraceID), strings.TrimSpace(envelope.DecisionID)
}
