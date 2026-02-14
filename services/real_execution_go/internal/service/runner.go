package service

import (
	"context"
	"errors"

	"open-trader/real_execution_go/internal/consumer"
)

type BodyHandler interface {
	Handle(ctx context.Context, body []byte) error
}

type Runner struct {
	QueueName string
	Consumer  consumer.MessageConsumer
	Handler   BodyHandler
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
				continue
			}
			return err
		}

		handleErr := r.Handler.Handle(ctx, delivery.Body)
		if handleErr != nil {
			if delivery.Nack != nil {
				_ = delivery.Nack(true)
			}
			continue
		}
		if delivery.Ack != nil {
			if ackErr := delivery.Ack(); ackErr != nil {
				return ackErr
			}
		}
	}
}
