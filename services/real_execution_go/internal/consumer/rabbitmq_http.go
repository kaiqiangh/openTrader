package consumer

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

type RabbitMQHTTPConsumer struct {
	APIBaseURL string
	Username   string
	Password   string
	Vhost      string
	HTTPClient *http.Client
}

func NewRabbitMQHTTPConsumer(
	apiBaseURL string,
	username string,
	password string,
	timeout time.Duration,
) *RabbitMQHTTPConsumer {
	return &RabbitMQHTTPConsumer{
		APIBaseURL: strings.TrimRight(apiBaseURL, "/"),
		Username:   username,
		Password:   password,
		Vhost:      "/",
		HTTPClient: &http.Client{Timeout: timeout},
	}
}

func NewRabbitMQHTTPConsumerFromEnv() *RabbitMQHTTPConsumer {
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
	return NewRabbitMQHTTPConsumer(apiBaseURL, username, password, timeout)
}

func (c *RabbitMQHTTPConsumer) Receive(ctx context.Context, queue string) (Delivery, error) {
	if strings.TrimSpace(queue) == "" {
		return Delivery{}, fmt.Errorf("queue name is required")
	}

	reqPayload := map[string]any{
		"count":    1,
		"ackmode":  "ack_requeue_false",
		"encoding": "auto",
		"truncate": 50000,
	}
	encoded, err := json.Marshal(reqPayload)
	if err != nil {
		return Delivery{}, fmt.Errorf("encode receive request: %w", err)
	}

	endpoint := fmt.Sprintf(
		"%s/queues/%s/%s/get",
		c.APIBaseURL,
		url.PathEscape(c.Vhost),
		url.PathEscape(queue),
	)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(encoded))
	if err != nil {
		return Delivery{}, fmt.Errorf("build receive request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept-Encoding", "identity")
	request.SetBasicAuth(c.Username, c.Password)

	response, err := c.httpClient().Do(request)
	if err != nil {
		return Delivery{}, fmt.Errorf("receive request failed: %w", err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode == http.StatusNotFound {
		return Delivery{}, ErrNoMessage
	}
	if response.StatusCode >= 300 {
		return Delivery{}, fmt.Errorf("receive request failed: status=%d body=%s", response.StatusCode, strings.TrimSpace(string(body)))
	}

	var rows []struct {
		Payload any `json:"payload"`
	}
	if err := json.Unmarshal(body, &rows); err != nil {
		return Delivery{}, fmt.Errorf("decode receive response: %w", err)
	}
	if len(rows) == 0 {
		return Delivery{}, ErrNoMessage
	}

	bodyBytes, err := payloadToJSONBytes(rows[0].Payload)
	if err != nil {
		return Delivery{}, err
	}
	return Delivery{
		Body: bodyBytes,
		Ack: func() error {
			return nil
		},
		Nack: func(requeue bool) error {
			_ = requeue
			return nil
		},
	}, nil
}

func payloadToJSONBytes(payload any) ([]byte, error) {
	switch value := payload.(type) {
	case string:
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			return nil, fmt.Errorf("rabbitmq payload is empty")
		}
		return []byte(trimmed), nil
	case map[string]any:
		encoded, err := json.Marshal(value)
		if err != nil {
			return nil, fmt.Errorf("encode payload object: %w", err)
		}
		return encoded, nil
	default:
		encoded, err := json.Marshal(value)
		if err != nil {
			return nil, fmt.Errorf("encode payload value: %w", err)
		}
		return encoded, nil
	}
}

func (c *RabbitMQHTTPConsumer) httpClient() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return &http.Client{Timeout: 2 * time.Second}
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
