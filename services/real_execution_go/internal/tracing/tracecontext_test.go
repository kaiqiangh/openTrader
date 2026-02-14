package tracing

import "testing"

func TestParseAndBuildTraceparentRoundTrip(t *testing.T) {
	input := "00-0123456789abcdef0123456789abcdef-89abcdef01234567-01"
	parsed, ok := ParseTraceparent(input)
	if !ok {
		t.Fatal("expected traceparent to parse")
	}
	if parsed.TraceID != "0123456789abcdef0123456789abcdef" {
		t.Fatalf("unexpected trace id: %s", parsed.TraceID)
	}
	if parsed.ParentSpanID != "89abcdef01234567" {
		t.Fatalf("unexpected parent span id: %s", parsed.ParentSpanID)
	}

	rebuilt := BuildTraceparent(parsed.TraceID, parsed.SpanID)
	rebuiltParsed, ok := ParseTraceparent(rebuilt)
	if !ok {
		t.Fatal("expected rebuilt traceparent to parse")
	}
	if rebuiltParsed.TraceID != parsed.TraceID {
		t.Fatalf("expected rebuilt trace id %s, got %s", parsed.TraceID, rebuiltParsed.TraceID)
	}
}

func TestParseTraceparentRejectsInvalidValue(t *testing.T) {
	if _, ok := ParseTraceparent("bad-value"); ok {
		t.Fatal("expected invalid traceparent to be rejected")
	}
}
