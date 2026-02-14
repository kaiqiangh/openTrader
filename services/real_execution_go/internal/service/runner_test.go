package service

import (
	"context"
	"errors"
	"testing"
	"time"

	"open-trader/real_execution_go/internal/consumer"
	"open-trader/real_execution_go/internal/metrics"
)

type fakeConsumer struct {
	deliveries []consumer.Delivery
	errors     []error
	index      int
}

func (f *fakeConsumer) Receive(ctx context.Context, queue string) (consumer.Delivery, error) {
	_ = ctx
	_ = queue
	if f.index < len(f.errors) && f.errors[f.index] != nil {
		err := f.errors[f.index]
		f.index++
		return consumer.Delivery{}, err
	}
	if f.index < len(f.deliveries) {
		d := f.deliveries[f.index]
		f.index++
		return d, nil
	}
	f.index++
	return consumer.Delivery{}, consumer.ErrNoMessage
}

type fakeBodyHandler struct {
	err   error
	calls int
}

func (h *fakeBodyHandler) Handle(ctx context.Context, body []byte) error {
	_ = ctx
	_ = body
	h.calls++
	return h.err
}

func TestRunnerReceivesAndAcksDelivery(t *testing.T) {
	acked := 0
	cons := &fakeConsumer{
		deliveries: []consumer.Delivery{
			{
				Body: []byte(`{"ok":true}`),
				Ack: func() error {
					acked++
					return nil
				},
			},
		},
	}
	handler := &fakeBodyHandler{}
	collector := metrics.NewCollector()
	runner := &Runner{
		QueueName: "execution.intent.real",
		Consumer:  cons,
		Handler:   handler,
		Metrics:   collector,
	}

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(10 * time.Millisecond)
		cancel()
	}()

	if err := runner.Run(ctx); err != nil {
		t.Fatalf("runner returned error: %v", err)
	}
	if handler.calls == 0 {
		t.Fatal("expected handler to be called")
	}
	if acked != 1 {
		t.Fatalf("expected exactly one ack, got %d", acked)
	}
	snapshot := collector.Snapshot()
	if snapshot.Totals.SuccessTotal != 1 {
		t.Fatalf("expected one successful run, got %d", snapshot.Totals.SuccessTotal)
	}
	if snapshot.Totals.AckTotal != 1 {
		t.Fatalf("expected one ack metric, got %d", snapshot.Totals.AckTotal)
	}
}

func TestRunnerNacksOnHandlerError(t *testing.T) {
	nacked := 0
	cons := &fakeConsumer{
		deliveries: []consumer.Delivery{
			{
				Body: []byte(`{"ok":false}`),
				Nack: func(requeue bool) error {
					_ = requeue
					nacked++
					return nil
				},
			},
		},
	}
	handler := &fakeBodyHandler{err: errors.New("boom")}
	collector := metrics.NewCollector()
	runner := &Runner{
		QueueName: "execution.intent.real",
		Consumer:  cons,
		Handler:   handler,
		Metrics:   collector,
	}

	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		time.Sleep(10 * time.Millisecond)
		cancel()
	}()

	if err := runner.Run(ctx); err != nil {
		t.Fatalf("runner returned error: %v", err)
	}
	if nacked != 1 {
		t.Fatalf("expected one nack, got %d", nacked)
	}
	snapshot := collector.Snapshot()
	if snapshot.Totals.FailureTotal == 0 {
		t.Fatal("expected failure metrics to be recorded")
	}
	if snapshot.Totals.NackTotal != 1 {
		t.Fatalf("expected one nack metric, got %d", snapshot.Totals.NackTotal)
	}
}
