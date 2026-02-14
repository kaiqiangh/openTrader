package metrics

import (
	"sync"
	"time"
)

type TraceSpan struct {
	QueueName  string
	Status     string
	LatencyMs  float64
	ErrorType  string
	RecordedAt string
}

type Totals struct {
	RunsTotal      int
	SuccessTotal   int
	FailureTotal   int
	AckTotal       int
	NackTotal      int
	NoMessageTotal int
}

type Snapshot struct {
	Totals       Totals
	AvgLatencyMs float64
	MaxLatencyMs float64
	RecentSpans  []TraceSpan
}

type Collector struct {
	mu        sync.Mutex
	totals    Totals
	latencies []float64
	spans     []TraceSpan
}

func NewCollector() *Collector {
	return &Collector{}
}

func (c *Collector) RecordNoMessage(queueName string) {
	_ = queueName
	c.mu.Lock()
	defer c.mu.Unlock()
	c.totals.NoMessageTotal++
}

func (c *Collector) RecordAck(queueName string) {
	_ = queueName
	c.mu.Lock()
	defer c.mu.Unlock()
	c.totals.AckTotal++
}

func (c *Collector) RecordNack(queueName string) {
	_ = queueName
	c.mu.Lock()
	defer c.mu.Unlock()
	c.totals.NackTotal++
}

func (c *Collector) RecordRunSuccess(queueName string, latency time.Duration) {
	c.mu.Lock()
	defer c.mu.Unlock()

	latencyMs := durationToMs(latency)
	c.totals.RunsTotal++
	c.totals.SuccessTotal++
	c.latencies = append(c.latencies, latencyMs)
	c.spans = append(c.spans, TraceSpan{
		QueueName:  queueName,
		Status:     "succeeded",
		LatencyMs:  latencyMs,
		ErrorType:  "",
		RecordedAt: utcNowISO(),
	})
}

func (c *Collector) RecordRunFailure(queueName string, latency time.Duration, errorType string) {
	c.mu.Lock()
	defer c.mu.Unlock()

	latencyMs := durationToMs(latency)
	c.totals.RunsTotal++
	c.totals.FailureTotal++
	c.latencies = append(c.latencies, latencyMs)
	c.spans = append(c.spans, TraceSpan{
		QueueName:  queueName,
		Status:     "failed",
		LatencyMs:  latencyMs,
		ErrorType:  errorType,
		RecordedAt: utcNowISO(),
	})
}

func (c *Collector) Snapshot() Snapshot {
	c.mu.Lock()
	defer c.mu.Unlock()

	avgLatency := 0.0
	maxLatency := 0.0
	if len(c.latencies) > 0 {
		sum := 0.0
		for _, latency := range c.latencies {
			sum += latency
			if latency > maxLatency {
				maxLatency = latency
			}
		}
		avgLatency = sum / float64(len(c.latencies))
	}

	recent := make([]TraceSpan, len(c.spans))
	copy(recent, c.spans)

	return Snapshot{
		Totals:       c.totals,
		AvgLatencyMs: avgLatency,
		MaxLatencyMs: maxLatency,
		RecentSpans:  recent,
	}
}

func durationToMs(value time.Duration) float64 {
	return float64(value.Microseconds()) / 1000.0
}

func utcNowISO() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}
