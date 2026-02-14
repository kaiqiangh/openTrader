package metrics

import (
	"testing"
	"time"
)

func TestCollectorTracksRunAndDeliveryMetrics(t *testing.T) {
	collector := NewCollector()

	collector.RecordNoMessage("execution.intent.real")
	collector.RecordAck("execution.intent.real")
	collector.RecordNack("execution.intent.real")
	collector.RecordRunSuccess("execution.intent.real", 12*time.Millisecond, "trace-1", "decision-1")
	collector.RecordRunFailure("execution.intent.real", 8*time.Millisecond, "handler_error", "trace-2", "decision-2")

	snapshot := collector.Snapshot()

	if snapshot.Totals.RunsTotal != 2 {
		t.Fatalf("expected runs_total=2, got %d", snapshot.Totals.RunsTotal)
	}
	if snapshot.Totals.SuccessTotal != 1 {
		t.Fatalf("expected success_total=1, got %d", snapshot.Totals.SuccessTotal)
	}
	if snapshot.Totals.FailureTotal != 1 {
		t.Fatalf("expected failure_total=1, got %d", snapshot.Totals.FailureTotal)
	}
	if snapshot.Totals.AckTotal != 1 {
		t.Fatalf("expected ack_total=1, got %d", snapshot.Totals.AckTotal)
	}
	if snapshot.Totals.NackTotal != 1 {
		t.Fatalf("expected nack_total=1, got %d", snapshot.Totals.NackTotal)
	}
	if snapshot.Totals.NoMessageTotal != 1 {
		t.Fatalf("expected no_message_total=1, got %d", snapshot.Totals.NoMessageTotal)
	}
	if len(snapshot.RecentSpans) != 2 {
		t.Fatalf("expected two trace spans, got %d", len(snapshot.RecentSpans))
	}
	if snapshot.RecentSpans[0].Status != "succeeded" {
		t.Fatalf("expected first span succeeded, got %s", snapshot.RecentSpans[0].Status)
	}
	if snapshot.RecentSpans[1].Status != "failed" {
		t.Fatalf("expected second span failed, got %s", snapshot.RecentSpans[1].Status)
	}
	if snapshot.RecentSpans[1].ErrorType != "handler_error" {
		t.Fatalf("expected failure error type handler_error, got %s", snapshot.RecentSpans[1].ErrorType)
	}
	if snapshot.RecentSpans[0].TraceID != "trace-1" {
		t.Fatalf("expected first span trace id trace-1, got %s", snapshot.RecentSpans[0].TraceID)
	}
	if snapshot.RecentSpans[1].DecisionID != "decision-2" {
		t.Fatalf("expected second span decision id decision-2, got %s", snapshot.RecentSpans[1].DecisionID)
	}
	if snapshot.AvgLatencyMs <= 0 {
		t.Fatalf("expected avg latency > 0, got %f", snapshot.AvgLatencyMs)
	}
	if snapshot.MaxLatencyMs <= 0 {
		t.Fatalf("expected max latency > 0, got %f", snapshot.MaxLatencyMs)
	}
}
