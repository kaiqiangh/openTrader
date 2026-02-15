package consumer

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestRabbitMQHTTPConsumerReceiveReturnsDelivery(t *testing.T) {
	consumer := NewRabbitMQHTTPConsumer("http://rabbitmq.local/api", "guest", "guest", 2*time.Second)
	consumer.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			if req.Method != http.MethodPost {
				t.Fatalf("expected POST, got %s", req.Method)
			}
			if req.Header.Get("Accept-Encoding") != "identity" {
				t.Fatalf("expected Accept-Encoding identity, got %q", req.Header.Get("Accept-Encoding"))
			}
			if !strings.Contains(req.URL.String(), "/queues/%2F/execution.intent.real/get") {
				t.Fatalf("unexpected request URL: %s", req.URL.String())
			}
			user, pass, ok := req.BasicAuth()
			if !ok || user != "guest" || pass != "guest" {
				t.Fatalf("unexpected basic auth values")
			}
			return mockHTTPResponse(http.StatusOK, `[{"payload":"{\"trace_id\":\"trace-1\",\"decision_id\":\"decision-1\",\"ok\":true}"}]`), nil
		}),
	}

	delivery, err := consumer.Receive(context.Background(), "execution.intent.real")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !strings.Contains(string(delivery.Body), `"trace_id":"trace-1"`) {
		t.Fatalf("unexpected delivery body: %s", string(delivery.Body))
	}
	if delivery.Ack == nil || delivery.Nack == nil {
		t.Fatal("expected non-nil ack/nack callbacks")
	}
	if err := delivery.Ack(); err != nil {
		t.Fatalf("unexpected ack error: %v", err)
	}
	if err := delivery.Nack(true); err != nil {
		t.Fatalf("unexpected nack error: %v", err)
	}
}

func TestRabbitMQHTTPConsumerReceiveNoMessage(t *testing.T) {
	consumer := NewRabbitMQHTTPConsumer("http://rabbitmq.local/api", "guest", "guest", 2*time.Second)
	consumer.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return mockHTTPResponse(http.StatusOK, `[]`), nil
		}),
	}

	_, err := consumer.Receive(context.Background(), "execution.intent.real")
	if !errors.Is(err, ErrNoMessage) {
		t.Fatalf("expected ErrNoMessage, got %v", err)
	}
}

func TestRabbitMQHTTPConsumerQueueNotFoundMapsToNoMessage(t *testing.T) {
	consumer := NewRabbitMQHTTPConsumer("http://rabbitmq.local/api", "guest", "guest", 2*time.Second)
	consumer.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return mockHTTPResponse(http.StatusNotFound, `{"error":"not_found","reason":"queue_not_found"}`), nil
		}),
	}

	_, err := consumer.Receive(context.Background(), "execution.intent.real")
	if !errors.Is(err, ErrNoMessage) {
		t.Fatalf("expected ErrNoMessage, got %v", err)
	}
}

func TestRabbitMQHTTPConsumerObjectNotFoundMapsToNoMessage(t *testing.T) {
	consumer := NewRabbitMQHTTPConsumer("http://rabbitmq.local/api", "guest", "guest", 2*time.Second)
	consumer.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return mockHTTPResponse(http.StatusNotFound, `{"error":"Object Not Found","reason":"Not Found"}`), nil
		}),
	}

	_, err := consumer.Receive(context.Background(), "execution.intent.real")
	if !errors.Is(err, ErrNoMessage) {
		t.Fatalf("expected ErrNoMessage, got %v", err)
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
