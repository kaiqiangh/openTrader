package idempotency

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

type RedisStore struct {
	client *redis.Client
	now    func() time.Time
	prefix string
	ttl    time.Duration
}

func NewRedisStore(redisURL string) (*RedisStore, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis url: %w", err)
	}
	client := redis.NewClient(opt)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis ping: %w", err)
	}

	return &RedisStore{
		client: client,
		now:    time.Now,
		prefix: "idempotency:",
		ttl:    24 * time.Hour,
	}, nil
}

func (s *RedisStore) TryStart(dispatchKey string) bool {
	ctx := context.Background()
	key := s.prefix + dispatchKey

	ok, err := s.client.SetNX(ctx, key, s.marshal(Record{
		DispatchKey: dispatchKey,
		Status:      StatusStarted,
		UpdatedAt:   s.now().UTC(),
	}), s.ttl).Result()
	if err != nil {
		// Redis error — fail open (allow execution) to avoid blocking trades
		return true
	}
	return ok
}

func (s *RedisStore) MarkCompleted(dispatchKey string, orderID string) {
	ctx := context.Background()
	key := s.prefix + dispatchKey
	_ = s.client.Set(ctx, key, s.marshal(Record{
		DispatchKey: dispatchKey,
		Status:      StatusCompleted,
		OrderID:     orderID,
		UpdatedAt:   s.now().UTC(),
	}), s.ttl).Err()
}

func (s *RedisStore) MarkFailed(dispatchKey string, lastError string) {
	ctx := context.Background()
	key := s.prefix + dispatchKey
	_ = s.client.Set(ctx, key, s.marshal(Record{
		DispatchKey: dispatchKey,
		Status:      StatusFailed,
		LastError:   lastError,
		UpdatedAt:   s.now().UTC(),
	}), s.ttl).Err()
}

func (s *RedisStore) Get(dispatchKey string) (Record, bool) {
	ctx := context.Background()
	key := s.prefix + dispatchKey

	data, err := s.client.Get(ctx, key).Bytes()
	if err != nil {
		return Record{}, false
	}

	var record Record
	if err := json.Unmarshal(data, &record); err != nil {
		return Record{}, false
	}
	return record, true
}

func (s *RedisStore) Close() error {
	return s.client.Close()
}

func (s *RedisStore) marshal(record Record) string {
	data, _ := json.Marshal(record)
	return string(data)
}
