package bridge

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"
)

type HTTPBridgeClient struct {
	EndpointURL string
	APIKey      string
	HTTPClient  *http.Client
}

func NewHTTPBridgeClient(endpointURL string, timeout time.Duration) *HTTPBridgeClient {
	return &HTTPBridgeClient{
		EndpointURL: strings.TrimSpace(endpointURL),
		HTTPClient:  &http.Client{Timeout: timeout},
	}
}

func NewHTTPBridgeClientFromEnv() *HTTPBridgeClient {
	endpoint := firstNonEmpty(
		os.Getenv("REAL_EXECUTION_BRIDGE_URL"),
		"http://api:8000/internal/execution/dispatch",
	)
	timeout := parseDurationMs(firstNonEmpty(os.Getenv("REAL_EXECUTION_BRIDGE_TIMEOUT_MS"), "3000"))
	client := NewHTTPBridgeClient(endpoint, timeout)
	client.APIKey = strings.TrimSpace(os.Getenv("REAL_EXECUTION_BRIDGE_API_KEY"))
	return client
}

func (c *HTTPBridgeClient) Execute(command Command) (Result, error) {
	if err := command.Validate(); err != nil {
		return Result{}, err
	}
	if strings.TrimSpace(c.EndpointURL) == "" {
		return Result{}, fmt.Errorf("bridge endpoint URL is required")
	}

	encoded, err := json.Marshal(command)
	if err != nil {
		return Result{}, fmt.Errorf("encode command: %w", err)
	}
	request, err := http.NewRequest(http.MethodPost, c.EndpointURL, bytes.NewReader(encoded))
	if err != nil {
		return Result{}, fmt.Errorf("build bridge request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	if c.APIKey != "" {
		request.Header.Set("Authorization", "Bearer "+c.APIKey)
	}

	response, err := c.httpClient().Do(request)
	if err != nil {
		return Result{}, fmt.Errorf("bridge request failed: %w", err)
	}
	defer response.Body.Close()
	body, _ := io.ReadAll(response.Body)
	if response.StatusCode >= 300 {
		return Result{}, fmt.Errorf("bridge request failed: status=%d body=%s", response.StatusCode, strings.TrimSpace(string(body)))
	}

	var parsed Result
	if err := json.Unmarshal(body, &parsed); err != nil {
		return Result{}, fmt.Errorf("decode bridge response: %w", err)
	}
	return parsed, nil
}

func (c *HTTPBridgeClient) httpClient() *http.Client {
	if c.HTTPClient != nil {
		return c.HTTPClient
	}
	return &http.Client{Timeout: 3 * time.Second}
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
		return 3 * time.Second
	}
	if ms <= 0 {
		return 3 * time.Second
	}
	return ms
}
