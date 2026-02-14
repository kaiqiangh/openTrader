# LLM Gateway Baseline (P3-006)

This document defines the initial centralized LLM gateway skeleton:

- `services/llm_gateway/contracts.py`
- `services/llm_gateway/gateway.py`
- `services/llm_gateway/__init__.py`

## Objective

Provide one service-layer contract for model requests that supports:

- provider alias/model configuration
- timeout and retry policies
- ordered provider fallback
- normalized response payloads for downstream persistence (`P3-007`)

## Contracts

1. `ProviderSettings`
- Alias, model, timeout, retry count, enable flag, and provider-specific extra kwargs.

2. `GatewaySettings`
- Provider map, default provider order, retry backoff bounds.

3. `LLMRequest`
- Required request metadata (`trace_id`, `decision_id`, `strategy_id`, `agent_name`), prompt messages, decoding parameters, metadata.

4. `LLMResponse`
- Provider/model selected, normalized output content, raw payload, usage, latency, and attempt count.

5. Errors
- `ProviderNotConfiguredError`
- `LLMRetryExhaustedError`

## Runtime Flow

1. Receive `LLMRequest` from caller.
2. Resolve provider order from explicit override or gateway defaults.
3. For each provider alias:
- validate provider settings and client presence
- execute provider call with timeout enforcement
- on error, retry with exponential backoff up to configured limit
- on exhaustion, move to next provider alias.
4. Return first successful `LLMResponse`.
5. If all providers fail, raise `LLMRetryExhaustedError` with summarized failure context.

## Extract/Normalization Rules

- Content extraction precedence:
  1. payload `content`
  2. `choices[0].message.content`
  3. `choices[0].text`
- Usage defaults to zero tokens when provider payload omits usage fields.
- Retry delay uses bounded exponential backoff from `GatewaySettings`.

## Notes for Next Phases

- `P3-007`: persist full request/response payloads and usage/latency metrics.
- `P3-008`: apply quota checks before gateway dispatch and hard-limit outcomes.
- `P3-009`: route gateway outputs through guardrail validation before intent publish.
