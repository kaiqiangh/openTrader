from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from services.agent_orchestrator.contracts import OrchestrationResult, StrategyConfig
from services.agent_orchestrator.execution_decision_agent import ExecutionDecisionAgent
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
        service_name: str = "agent_orchestrator",
    ) -> None:
        self.publisher = publisher
        self.planner_agent = planner_agent or PlannerAgent()
        self.risk_agent = risk_agent or RiskAgent()
        self.execution_decision_agent = execution_decision_agent or ExecutionDecisionAgent()
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
        market_context = self._build_market_context(payload=envelope["payload"], strategy=strategy)

        plan = self.planner_agent.build_plan(market_context=market_context, strategy=strategy)
        risk = self.risk_agent.evaluate(plan=plan, market_context=market_context, strategy=strategy)
        execution_decision = self.execution_decision_agent.propose_action(
            plan=plan,
            risk=risk,
            market_context=market_context,
            strategy=strategy,
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

        status = "RISK_APPROVED" if risk.approved else "RISK_REJECTED"
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

        execution_intent: dict[str, Any] | None = None
        should_publish_intent = (
            risk.approved
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
            plan=plan,
            risk=risk,
            execution_decision=execution_decision,
            execution_intent=execution_intent,
        )

    def _build_market_context(
        self,
        *,
        payload: Mapping[str, Any],
        strategy: StrategyConfig,
    ) -> dict[str, Any]:
        best_bid, best_bid_size = self._extract_level(payload.get("bids"), side="bid")
        best_ask, best_ask_size = self._extract_level(payload.get("asks"), side="ask")

        if best_bid is not None and best_ask is not None:
            mid_price = (best_bid + best_ask) / 2.0
        else:
            mid_price = float(payload.get("mid_price", 0.0))

        return {
            "exchange": payload.get("exchange", "unknown"),
            "symbol": payload.get("symbol", strategy.symbol),
            "timestamp_ms": payload.get("timestamp_ms"),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "best_bid_size": best_bid_size,
            "best_ask_size": best_ask_size,
            "mid_price": mid_price,
            "current_position": float(payload.get("current_position", 0.0)),
            "drawdown_pct": float(payload.get("drawdown_pct", 0.0)),
        }

    @staticmethod
    def _extract_level(levels: Any, *, side: str) -> tuple[float | None, float]:
        if not isinstance(levels, list) or len(levels) == 0:
            return None, 0.0

        parsed: list[tuple[float, float]] = []
        for level in levels:
            if not isinstance(level, Mapping):
                continue
            try:
                price = float(level["price"])
                size = float(level["amount"])
            except (KeyError, TypeError, ValueError):
                continue
            parsed.append((price, max(0.0, size)))

        if not parsed:
            return None, 0.0

        if side == "bid":
            price, size = max(parsed, key=lambda item: item[0])
            return price, size

        price, size = min(parsed, key=lambda item: item[0])
        return price, size

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
