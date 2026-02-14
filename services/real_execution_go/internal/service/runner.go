package service

import (
	"context"
	"errors"
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
				r.Metrics.RecordRunFailure(r.QueueName, 0, "consumer_error")
			}
			return err
		}

		started := time.Now()
		handleErr := r.Handler.Handle(ctx, delivery.Body)
		if handleErr != nil {
			if delivery.Nack != nil {
				_ = delivery.Nack(true)
				if r.Metrics != nil {
					r.Metrics.RecordNack(r.QueueName)
				}
			}
			if r.Metrics != nil {
				r.Metrics.RecordRunFailure(r.QueueName, time.Since(started), "handler_error")
			}
			continue
		}
		if delivery.Ack != nil {
			if ackErr := delivery.Ack(); ackErr != nil {
				if r.Metrics != nil {
					r.Metrics.RecordRunFailure(r.QueueName, time.Since(started), "ack_error")
				}
				return ackErr
			}
			if r.Metrics != nil {
				r.Metrics.RecordAck(r.QueueName)
			}
		}
		if r.Metrics != nil {
			r.Metrics.RecordRunSuccess(r.QueueName, time.Since(started))
		}
	}
}
