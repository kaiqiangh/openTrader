package bridge

import (
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

func TestHTTPBridgeClientExecuteSuccess(t *testing.T) {
	client := NewHTTPBridgeClient("http://bridge.local/dispatch", 2*time.Second)
	client.APIKey = "test-key"
	client.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			if req.Method != http.MethodPost {
				t.Fatalf("expected POST, got %s", req.Method)
			}
			if got := req.Header.Get("Authorization"); got != "Bearer test-key" {
				t.Fatalf("expected bearer auth header, got %q", got)
			}
			return mockHTTPResponse(http.StatusOK, `{"order_id":"order-1","status":"submitted","raw_response":{"ok":true}}`), nil
		}),
	}
	command := NewCreateOrderCommand(
		"cmd-1",
		"idem-1",
		ActionBuy,
		"BTC/USDT",
		0.2,
		"trace-1",
		"decision-1",
		"client-1",
	)

	result, err := client.Execute(command)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if result.OrderID != "order-1" {
		t.Fatalf("expected order-1, got %s", result.OrderID)
	}
	if strings.ToUpper(result.Status) != "SUBMITTED" {
		t.Fatalf("expected submitted status, got %s", result.Status)
	}
}

func TestHTTPBridgeClientExecuteReturnsErrorOnNonSuccessStatus(t *testing.T) {
	client := NewHTTPBridgeClient("http://bridge.local/dispatch", 2*time.Second)
	client.HTTPClient = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return mockHTTPResponse(http.StatusBadGateway, `{"error":"bridge_unavailable"}`), nil
		}),
	}
	command := NewCreateOrderCommand(
		"cmd-2",
		"idem-2",
		ActionSell,
		"BTC/USDT",
		0.1,
		"trace-2",
		"decision-2",
		"client-2",
	)

	if _, err := client.Execute(command); err == nil {
		t.Fatal("expected execute error")
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
