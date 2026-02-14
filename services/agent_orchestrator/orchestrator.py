from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from services.agent_orchestrator.contracts import OrchestrationResult, StrategyConfig
from services.agent_orchestrator.execution_decision_agent import ExecutionDecisionAgent
from services.agent_orchestrator.guardrail_validation import GuardrailValidationLayer
from services.agent_orchestrator.market_context_agent import MarketContextAgent
from services.agent_orchestrator.planner_agent import PlannerAgent
from services.agent_orchestrator.risk_agent import RiskAgent
from services.shared.contracts.message_envelope import validate_envelope


class DecisionPublisher(Protocol):
    async def publish(self, *, routing_key: str, message: Mapping[str, Any]) -> None: ...


class AgentOrchestrator:
    def __init__(
        self,
        *,
        publisher: DecisionPublisher,
        planner_agent: PlannerAgent | None = None,
        risk_agent: RiskAgent | None = None,
        execution_decision_agent: ExecutionDecisionAgent | None = None,
        market_context_agent: MarketContextAgent | None = None,
        guardrail_validation_layer: GuardrailValidationLayer | None = None,
        service_name: str = "agent_orchestrator",
    ) -> None:
        self.publisher = publisher
        self.planner_agent = planner_agent or PlannerAgent()
        self.risk_agent = risk_agent or RiskAgent()
        self.execution_decision_agent = execution_decision_agent or ExecutionDecisionAgent()
        self.market_context_agent = market_context_agent or MarketContextAgent()
        self.guardrail_validation_layer = guardrail_validation_layer or GuardrailValidationLayer()
        self.service_name = service_name

    async def handle_market_event(
        self,
        envelope: Mapping[str, Any],
        *,
        strategy: StrategyConfig,
    ) -> OrchestrationResult:
        validate_envelope(envelope)
        if not str(envelope.get("event_type", "")).startswith("market.canonical"):
            raise ValueError("AgentOrchestrator expects market.canonical envelopes")

        mode = str(envelope["mode"])
        trace_id = str(envelope["trace_id"])
        decision_id = str(envelope["decision_id"])
        context_output = self.market_context_agent.enrich(
            payload=envelope["payload"],
            strategy=strategy,
        )
        market_context = context_output.context

        plan = self.planner_agent.build_plan(market_context=market_context, strategy=strategy)
        risk = self.risk_agent.evaluate(plan=plan, market_context=market_context, strategy=strategy)
        execution_decision = self.execution_decision_agent.propose_action(
            plan=plan,
            risk=risk,
            market_context=market_context,
            strategy=strategy,
        )
        guardrail = self.guardrail_validation_layer.validate(
            strategy=strategy,
            market_context=market_context,
            plan=plan,
            risk=risk,
            decision=execution_decision,
        )

        lifecycle = [
            self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type="agent.decision.received",
                idempotency_key=f"agent.decision.received:{decision_id}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                },
            ),
            self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type="agent.decision.context_enriched",
                idempotency_key=f"agent.decision.context_enriched:{decision_id}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                    "microstructure": context_output.microstructure,
                    "news": {
                        "summary": context_output.news["summary"],
                        "sentiment": context_output.news["sentiment"],
                        "source_count": context_output.news["source_count"],
                    },
                    "quality": context_output.quality,
                    "notes": list(context_output.notes),
                },
            ),
            self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type="agent.decision.planned",
                idempotency_key=f"agent.decision.planned:{decision_id}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                    "action": plan.action,
                    "target_quantity": plan.target_quantity,
                    "confidence": plan.confidence,
                    "metrics": plan.metrics,
                },
            ),
        ]

        if not risk.approved:
            status = "RISK_REJECTED"
        elif not guardrail.allowed:
            status = "GUARDRAIL_REJECTED"
        else:
            status = "RISK_APPROVED"
        lifecycle.append(
            self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type=(
                    "agent.decision.risk_approved" if risk.approved else "agent.decision.risk_rejected"
                ),
                idempotency_key=f"agent.decision.risk:{decision_id}:{status}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                    "approved": risk.approved,
                    "blocked_by": list(risk.blocked_by),
                    "risk_score": risk.risk_score,
                },
            )
        )
        lifecycle.append(
            self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type="agent.decision.action_proposed",
                idempotency_key=f"agent.decision.action_proposed:{decision_id}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                    "action": execution_decision.action,
                    "quantity": execution_decision.quantity,
                    "confidence": execution_decision.confidence,
                    "constraints": execution_decision.constraints,
                },
            )
        )
        lifecycle.append(
            self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type=(
                    "agent.decision.guardrail_passed"
                    if guardrail.allowed
                    else "agent.decision.guardrail_rejected"
                ),
                idempotency_key=f"agent.decision.guardrail:{decision_id}:{'pass' if guardrail.allowed else 'reject'}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                    "allowed": guardrail.allowed,
                    "blocked_by": list(guardrail.blocked_by),
                    "checks": guardrail.checks,
                    "violations": [
                        {
                            "code": violation.code,
                            "message": violation.message,
                            "details": violation.details,
                        }
                        for violation in guardrail.violations
                    ],
                },
            )
        )

        execution_intent: dict[str, Any] | None = None
        should_publish_intent = (
            risk.approved
            and guardrail.allowed
            and execution_decision.constraints.get("schema_valid", False)
            and execution_decision.action in {"BUY", "SELL", "CLOSE"}
            and execution_decision.quantity != 0.0
        )
        if should_publish_intent:
            execution_intent = self._build_envelope(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                event_type="execution.intent.created",
                idempotency_key=f"execution.intent:{mode.lower()}:{decision_id}",
                payload={
                    "strategy_id": strategy.strategy_id,
                    "symbol": market_context["symbol"],
                    "action": execution_decision.action,
                    "quantity": execution_decision.quantity,
                    "confidence": execution_decision.confidence,
                    "rationale": list(execution_decision.rationale),
                    "constraints": execution_decision.constraints,
                    "market_context": {
                        "mid_price": market_context["mid_price"],
                        "best_bid": market_context["best_bid"],
                        "best_ask": market_context["best_ask"],
                        "spread_bps": market_context["spread_bps"],
                        "orderbook_imbalance": market_context["orderbook_imbalance"],
                        "microstructure_regime": market_context["microstructure_regime"],
                        "news_summary": market_context["news_summary"],
                        "news_sentiment": market_context["news_sentiment"],
                    },
                },
            )
            lifecycle.append(
                self._build_envelope(
                    trace_id=trace_id,
                    decision_id=decision_id,
                    mode=mode,
                    event_type="agent.decision.intent_published",
                    idempotency_key=f"agent.decision.intent_published:{decision_id}",
                    payload={
                        "strategy_id": strategy.strategy_id,
                        "symbol": market_context["symbol"],
                        "routing_key": self._routing_key_for_mode(mode),
                        "action": execution_decision.action,
                    },
                )
            )
            await self.publisher.publish(
                routing_key=self._routing_key_for_mode(mode),
                message=execution_intent,
            )

        for lifecycle_event in lifecycle:
            await self.publisher.publish(
                routing_key="strategy.decision.lifecycle",
                message=lifecycle_event,
            )

        return OrchestrationResult(
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            status=status,
            lifecycle=tuple(lifecycle),
            market_context=context_output,
            plan=plan,
            risk=risk,
            execution_decision=execution_decision,
            guardrail=guardrail,
            execution_intent=execution_intent,
        )

    @staticmethod
    def _routing_key_for_mode(mode: str) -> str:
        normalized = mode.upper()
        if normalized == "MOCK":
            return "execution.intent.mock"
        if normalized == "REAL":
            return "execution.intent.real"
        raise ValueError(f"Unsupported mode for routing key: {mode}")

    def _build_envelope(
        self,
        *,
        trace_id: str,
        decision_id: str,
        mode: str,
        event_type: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        envelope = {
            "trace_id": trace_id,
            "decision_id": decision_id,
            "mode": mode,
            "idempotency_key": idempotency_key,
            "event_type": event_type,
            "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": dict(payload),
            "service": self.service_name,
        }
        validate_envelope(envelope)
        return envelope
