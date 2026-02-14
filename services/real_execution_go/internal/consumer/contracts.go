package consumer

import (
	"context"
	"errors"
)

var ErrNoMessage = errors.New("no message available")

type Delivery struct {
	Body []byte
	Ack  func() error
	Nack func(requeue bool) error
}

type MessageConsumer interface {
	Receive(ctx context.Context, queue string) (Delivery, error)
}
