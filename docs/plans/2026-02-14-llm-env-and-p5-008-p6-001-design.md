# LLM Env Review + P5-008/P5-009/P6-001 Design

## Scope

1. Review whether LLM-related `.env` keys are repetitive and whether the current LLM client boundary is sound.
2. Deliver `P5-008` risk observability.
3. Deliver `P5-009` risk regression scenarios.
4. Deliver `P6-001` source connector framework.

## Findings: LLM Env Keys

Current keys:
- `LITELLM_BASE_URL`
- `LITELLM_API_KEY`
- `LITELLM_TIMEOUT_SECONDS`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Code review result:
- App runtime currently implements a LiteLLM HTTP adapter (`services/llm_gateway/litellm_http_adapter.py`) and provider-agnostic gateway contracts.
- `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` are not directly consumed by app code today.
- They can still be valid as upstream credentials for a co-located LiteLLM router.

Decision:
- Keep both key classes but clarify semantics in docs/env comments:
  - LiteLLM keys are consumed by openTrader runtime.
  - OpenAI/Anthropic keys are optional upstream provider credentials for LiteLLM deployment, not direct app runtime inputs yet.

## Design Options

### Option A (Recommended)

- Add dedicated OMS risk observability module and wire it as an optional sink in `RiskPolicyEngine`.
- Add scenario-rich regression tests for rule/guard/control edge cases.
- Add a pluggable connector registry + cycle runner for `news_ingestion` with graceful degradation on connector failure.

Pros:
- Clear module boundaries.
- Extensible for future API/notification integration.
- Keeps deterministic contracts with explicit risk telemetry.

Cons:
- Introduces new modules and test surface.

### Option B

- Add ad hoc counters directly inside `risk_policy.py` and skip dedicated observability module.

Cons:
- Tight coupling and weak reuse for APIs/ops dashboards.

### Option C

- Implement connector framework only and defer risk observability/regression.

Cons:
- Does not satisfy current phase task goals.

## Selected Architecture

- `services/oms/risk_observability.py`
  - Collects risk policy decision metrics/events and control-plane events.
- `services/oms/risk_policy.py`
  - Accepts optional observability sink and emits telemetry on evaluate/control-event drain.
- `tests/test_p5_risk_observability.py`
  - Unit coverage for counters, severity mapping, and event draining.
- `tests/test_p5_risk_regression.py`
  - Cross-cutting scenarios for limits, guards, and emergency controls.
- `services/news_ingestion/source_connectors.py`
  - Pluggable connector protocol + registry + resilient cycle runner.
- `tests/test_p6_source_connectors.py`
  - Registry, aggregation, and fault-isolation tests.

## Documentation Updates

- `.env.example`: clarify LLM key semantics; avoid misleading duplication interpretation.
- `README.md` + `docs/llm_gateway_baseline.md`: document LiteLLM runtime contract and optional upstream credentials.
- `docs/IMPLEMENTATION_PLAN.md`: mark completed tasks and roll next actions.
- `services/oms/AGENT.md` and `services/news_ingestion/AGENT.md`: add new module contracts/boundaries.
