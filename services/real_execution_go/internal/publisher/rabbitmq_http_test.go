package publisher

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestRabbitMQHTTPPublisherPublishSuccess(t *testing.T) {
	pub := NewRabbitMQHTTPPublisher("http://rabbitmq.local/api", "guest", "guest", 2*time.Second)
	pub.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			if req.Method != http.MethodPost {
				t.Fatalf("expected POST, got %s", req.Method)
			}
			if !strings.Contains(req.URL.String(), "/exchanges/%2F/oms.events/publish") {
				t.Fatalf("unexpected request URL: %s", req.URL.String())
			}
			var payload map[string]any
			if err := json.NewDecoder(req.Body).Decode(&payload); err != nil {
				t.Fatalf("decode payload: %v", err)
			}
			if payload["routing_key"] != "oms.order.submitted" {
				t.Fatalf("unexpected routing key: %v", payload["routing_key"])
			}
			return mockHTTPResponse(http.StatusOK, `{"routed":true}`), nil
		}),
	}

	err := pub.Publish(
		context.Background(),
		"oms.order.submitted",
		map[string]any{"trace_id": "trace-1"},
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestRabbitMQHTTPPublisherPublishFailsWhenNotRouted(t *testing.T) {
	pub := NewRabbitMQHTTPPublisher("http://rabbitmq.local/api", "guest", "guest", 2*time.Second)
	pub.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return mockHTTPResponse(http.StatusOK, `{"routed":false}`), nil
		}),
	}

	if err := pub.Publish(
		context.Background(),
		"oms.order.submitted",
		map[string]any{"trace_id": "trace-1"},
	); err == nil {
		t.Fatal("expected publish error when message is not routed")
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func mockHTTPResponse(status int, body string) *http.Response {
	return &http.Response{
		StatusCode: status,
		Body:       io.NopCloser(strings.NewReader(body)),
		Header:     make(http.Header),
	}
}
