package publisher

import "context"

type MessagePublisher interface {
	Publish(ctx context.Context, routingKey string, message map[string]any) error
}
