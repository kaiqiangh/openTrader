package tracing

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"regexp"
	"strings"
)

var traceparentPattern = regexp.MustCompile(`^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$`)

type TraceContext struct {
	TraceID      string
	ParentSpanID string
	SpanID       string
	Sampled      bool
}

func NewTraceID() string {
	return randomHex(16)
}

func NewSpanID() string {
	return randomHex(8)
}

func BuildTraceparent(traceID string, spanID string) string {
	resolvedTraceID := strings.TrimSpace(strings.ToLower(traceID))
	if resolvedTraceID == "" {
		resolvedTraceID = NewTraceID()
	}
	resolvedSpanID := strings.TrimSpace(strings.ToLower(spanID))
	if resolvedSpanID == "" {
		resolvedSpanID = NewSpanID()
	}
	return fmt.Sprintf("00-%s-%s-01", resolvedTraceID, resolvedSpanID)
}

func ParseTraceparent(value string) (TraceContext, bool) {
	normalized := strings.TrimSpace(strings.ToLower(value))
	match := traceparentPattern.FindStringSubmatch(normalized)
	if match == nil {
		return TraceContext{}, false
	}
	return TraceContext{
		TraceID:      match[1],
		ParentSpanID: match[2],
		SpanID:       NewSpanID(),
		Sampled:      match[3] != "00",
	}, true
}

func ResolveTraceparent(value string) TraceContext {
	if parsed, ok := ParseTraceparent(value); ok {
		return parsed
	}
	return TraceContext{
		TraceID:      NewTraceID(),
		ParentSpanID: "",
		SpanID:       NewSpanID(),
		Sampled:      true,
	}
}

func randomHex(byteLen int) string {
	buf := make([]byte, byteLen)
	if _, err := rand.Read(buf); err != nil {
		return strings.Repeat("0", byteLen*2)
	}
	return hex.EncodeToString(buf)
}
