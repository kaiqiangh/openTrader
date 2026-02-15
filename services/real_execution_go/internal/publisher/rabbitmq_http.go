package publisher

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type RabbitMQHTTPPublisher struct {
	APIBaseURL       string
	Username         string
	Password         string
	Vhost            string
	HTTPClient       *http.Client
	exchangeByPrefix map[string]string
}

func NewRabbitMQHTTPPublisher(
	apiBaseURL string,
	username string,
	password string,
	timeout time.Duration,
) *RabbitMQHTTPPublisher {
	client := &http.Client{Timeout: timeout}
	return &RabbitMQHTTPPublisher{
		APIBaseURL: strings.TrimRight(apiBaseURL, "/"),
		Username:   username,
		Password:   password,
		Vhost:      "/",
		HTTPClient: client,
		exchangeByPrefix: map[string]string{
			"oms.":       "oms.events",
			"execution.": "execution.events",
		},
	}
}

func NewRabbitMQHTTPPublisherFromEnv() *RabbitMQHTTPPublisher {
	apiBaseURL := firstNonEmpty(
		os.Getenv("RUNTIME_RABBITMQ_HTTP_API_URL"),
		os.Getenv("NOTIFY_RABBITMQ_HTTP_API_URL"),
		"http://rabbitmq:15672/api",
	)
	username := firstNonEmpty(
		os.Getenv("RABBITMQ_DEFAULT_USER"),
		"guest",
	)
	password := firstNonEmpty(
		os.Getenv("RABBITMQ_DEFAULT_PASS"),
		"guest",
	)
	timeout := parseDurationMs(firstNonEmpty(os.Getenv("RUNTIME_BROKER_HTTP_TIMEOUT_MS"), "2000"))
	return NewRabbitMQHTTPPublisher(apiBaseURL, username, password, timeout)
}

func (p *RabbitMQHTTPPublisher) Publish(ctx context.Context, routingKey string, message map[string]any) error {
	if strings.TrimSpace(routingKey) == "" {
		return fmt.Errorf("routing key is required")
	}
	exchangeName, ok := p.resolveExchange(routingKey)
	if !ok {
		return fmt.Errorf("unable to resolve exchange for routing key %q", routingKey)
	}

	encodedMessage, err := json.Marshal(message)
	if err != nil {
		return fmt.Errorf("encode message: %w", err)
	}

	reqPayload := map[string]any{
		"properties":       map[string]any{},
		"routing_key":      routingKey,
		"payload":          string(encodedMessage),
		"payload_encoding": "string",
	}
	encodedRequest, err := json.Marshal(reqPayload)
	if err != nil {
		return fmt.Errorf("encode publish request: %w", err)
	}

	endpoint := fmt.Sprintf(
		"%s/exchanges/%s/%s/publish",
		p.APIBaseURL,
		url.PathEscape(p.Vhost),
		url.PathEscape(exchangeName),
	)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(encodedRequest))
	if err != nil {
		return fmt.Errorf("build publish request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.SetBasicAuth(p.Username, p.Password)

	response, err := p.httpClient().Do(request)
	if err != nil {
		return fmt.Errorf("publish request failed: %w", err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode >= 300 {
		return fmt.Errorf("publish request failed: status=%d body=%s", response.StatusCode, strings.TrimSpace(string(body)))
	}

	var parsed struct {
		Routed bool `json:"routed"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return fmt.Errorf("decode publish response: %w", err)
	}
	if !parsed.Routed {
		return fmt.Errorf("publish request was accepted but not routed")
	}
	return nil
}

func (p *RabbitMQHTTPPublisher) resolveExchange(routingKey string) (string, bool) {
	for prefix, exchange := range p.exchangeByPrefix {
		if strings.HasPrefix(routingKey, prefix) {
			return exchange, true
		}
	}
	return "", false
}

func (p *RabbitMQHTTPPublisher) httpClient() *http.Client {
	if p.HTTPClient != nil {
		return p.HTTPClient
	}
	return &http.Client{Timeout: 2 * time.Second}
}

func parseDurationMs(value string) time.Duration {
	ms, err := time.ParseDuration(strings.TrimSpace(value) + "ms")
	if err != nil {
		return 2 * time.Second
	}
	if ms <= 0 {
		return 2 * time.Second
	}
	return ms
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			return trimmed
		}
	}
	return ""
}
