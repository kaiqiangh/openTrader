from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import time
from typing import Any, Mapping, Protocol

from services.agent_orchestrator.contracts import OrchestrationResult, StrategyConfig
from services.agent_orchestrator.execution_decision_agent import ExecutionDecisionAgent
from services.agent_orchestrator.guardrail_validation import GuardrailValidationLayer
from services.agent_orchestrator.llm_runtime import LLMDecisionRuntime
from services.agent_orchestrator.market_context_agent import MarketContextAgent
from services.agent_orchestrator.metrics_tracing import AgentRuntimeMetrics
from services.agent_orchestrator.memory_layer import AgentMemoryLayer
from services.agent_orchestrator.planner_agent import PlannerAgent
from services.agent_orchestrator.risk_agent import RiskAgent
from services.notification_service.publishers import NotificationEventBridge
from services.simulation_execution.mode_routing import assert_no_mode_leakage, route_execution_intent
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
        memory_layer: AgentMemoryLayer | None = None,
        metrics: AgentRuntimeMetrics | None = None,
        llm_runtime: LLMDecisionRuntime | None = None,
        notification_bridge: NotificationEventBridge | None = None,
        service_name: str = "agent_orchestrator",
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.publisher = publisher
        self.planner_agent = planner_agent or PlannerAgent()
        self.risk_agent = risk_agent or RiskAgent()
        self.execution_decision_agent = execution_decision_agent or ExecutionDecisionAgent()
        self.market_context_agent = market_context_agent or MarketContextAgent()
        self.guardrail_validation_layer = guardrail_validation_layer or GuardrailValidationLayer()
        self.memory_layer = memory_layer or AgentMemoryLayer()
        self.metrics = metrics or AgentRuntimeMetrics()
        self.llm_runtime = llm_runtime
        self.notification_bridge = notification_bridge
        self.service_name = service_name
        self._monotonic_clock = monotonic_clock

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
        await self._run_async_stage(
            stage="memory_read",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.memory_layer.read_decision_memory(
                mode=mode,
                strategy_id=strategy.strategy_id,
                decision_id=decision_id,
            ),
        )
        context_output = self._run_sync_stage(
            stage="market_context_agent",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.market_context_agent.enrich(
                payload=envelope["payload"],
                strategy=strategy,
            ),
        )
        market_context = context_output.context
        await self.memory_layer.write_decision_slot(
            mode=mode,
            strategy_id=strategy.strategy_id,
            decision_id=decision_id,
            slot="context",
            payload={
                "market_context": market_context,
                "microstructure": context_output.microstructure,
                "news": context_output.news,
                "quality": context_output.quality,
                "notes": list(context_output.notes),
            },
        )

        plan = self._run_sync_stage(
            stage="planner_agent",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.planner_agent.build_plan(
                market_context=market_context,
                strategy=strategy,
            ),
        )
        if self.llm_runtime is not None:
            plan = await self._run_async_stage(
                stage="planner_llm",
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                operation=lambda: self._apply_planner_llm_suggestion(
                    trace_id=trace_id,
                    decision_id=decision_id,
                    strategy=strategy,
                    market_context=market_context,
                    plan=plan,
                ),
            )
        await self.memory_layer.write_decision_slot(
            mode=mode,
            strategy_id=strategy.strategy_id,
            decision_id=decision_id,
            slot="plan",
            payload={
                "action": plan.action,
                "confidence": plan.confidence,
                "target_quantity": plan.target_quantity,
                "rationale": list(plan.rationale),
                "metrics": plan.metrics,
            },
        )
        risk = self._run_sync_stage(
            stage="risk_agent",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.risk_agent.evaluate(
                plan=plan,
                market_context=market_context,
                strategy=strategy,
            ),
        )
        if self.llm_runtime is not None:
            risk = await self._run_async_stage(
                stage="risk_llm",
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                operation=lambda: self._apply_risk_llm_suggestion(
                    trace_id=trace_id,
                    decision_id=decision_id,
                    strategy=strategy,
                    market_context=market_context,
                    plan=plan,
                    risk=risk,
                ),
            )
        await self.memory_layer.write_decision_slot(
            mode=mode,
            strategy_id=strategy.strategy_id,
            decision_id=decision_id,
            slot="risk",
            payload={
                "approved": risk.approved,
                "approved_quantity": risk.approved_quantity,
                "blocked_by": list(risk.blocked_by),
                "risk_score": risk.risk_score,
                "signals": [
                    {
                        "name": signal.name,
                        "passed": signal.passed,
                        "value": signal.value,
                        "limit": signal.limit,
                        "message": signal.message,
                    }
                    for signal in risk.signals
                ],
            },
        )
        execution_decision = self._run_sync_stage(
            stage="execution_decision_agent",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.execution_decision_agent.propose_action(
                plan=plan,
                risk=risk,
                market_context=market_context,
                strategy=strategy,
            ),
        )
        if self.llm_runtime is not None:
            execution_decision = await self._run_async_stage(
                stage="execution_decision_llm",
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                operation=lambda: self._apply_execution_llm_suggestion(
                    trace_id=trace_id,
                    decision_id=decision_id,
                    strategy=strategy,
                    market_context=market_context,
                    plan=plan,
                    risk=risk,
                    execution_decision=execution_decision,
                ),
            )
        await self.memory_layer.write_decision_slot(
            mode=mode,
            strategy_id=strategy.strategy_id,
            decision_id=decision_id,
            slot="execution_decision",
            payload={
                "action": execution_decision.action,
                "quantity": execution_decision.quantity,
                "confidence": execution_decision.confidence,
                "rationale": list(execution_decision.rationale),
                "constraints": execution_decision.constraints,
            },
        )
        guardrail = self._run_sync_stage(
            stage="guardrail_validation",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.guardrail_validation_layer.validate(
                strategy=strategy,
                market_context=market_context,
                plan=plan,
                risk=risk,
                decision=execution_decision,
            ),
        )
        await self.memory_layer.write_decision_slot(
            mode=mode,
            strategy_id=strategy.strategy_id,
            decision_id=decision_id,
            slot="guardrail",
            payload={
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
        await self.memory_layer.write_decision_slot(
            mode=mode,
            strategy_id=strategy.strategy_id,
            decision_id=decision_id,
            slot="status",
            payload={"status": status},
        )
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
            exchange = str(market_context.get("exchange", "binance")).strip().lower() or "binance"
            order_type = str(execution_decision.constraints.get("order_type", "MARKET")).strip().upper() or "MARKET"
            time_in_force = execution_decision.constraints.get("time_in_force")
            limit_price = execution_decision.constraints.get("limit_price")
            trigger_price = execution_decision.constraints.get("trigger_price")
            if not isinstance(time_in_force, str) or not time_in_force.strip():
                time_in_force = "GTC" if order_type == "LIMIT" else None
            reduce_only = bool(execution_decision.action == "CLOSE")
            client_order_id = str(
                execution_decision.constraints.get("client_order_id", f"{strategy.strategy_id}-{decision_id[:12]}")
            )
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
                    "exchange": exchange,
                    "order_type": order_type,
                    "time_in_force": time_in_force,
                    "limit_price": limit_price,
                    "trigger_price": trigger_price,
                    "reduce_only": reduce_only,
                    "client_order_id": client_order_id,
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
            routing_key = route_execution_intent(execution_intent)
            assert_no_mode_leakage(routing_key=routing_key, envelope=execution_intent)
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
                        "routing_key": routing_key,
                        "action": execution_decision.action,
                    },
                )
            )
            await self.publisher.publish(
                routing_key=routing_key,
                message=execution_intent,
            )

        await self._run_async_stage(
            stage="memory_persist",
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            operation=lambda: self.memory_layer.persist_decision_summary(
                trace_id=trace_id,
                decision_id=decision_id,
                strategy_id=strategy.strategy_id,
                mode=mode,
                status=status,
                market_context=market_context,
                plan={
                    "action": plan.action,
                    "confidence": plan.confidence,
                    "target_quantity": plan.target_quantity,
                    "rationale": list(plan.rationale),
                    "metrics": plan.metrics,
                },
                risk={
                    "approved": risk.approved,
                    "approved_quantity": risk.approved_quantity,
                    "blocked_by": list(risk.blocked_by),
                    "risk_score": risk.risk_score,
                },
                execution_decision={
                    "action": execution_decision.action,
                    "quantity": execution_decision.quantity,
                    "confidence": execution_decision.confidence,
                    "rationale": list(execution_decision.rationale),
                    "constraints": execution_decision.constraints,
                },
                guardrail={
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
                lifecycle=tuple(lifecycle),
            ),
        )

        for lifecycle_event in lifecycle:
            await self.publisher.publish(
                routing_key="strategy.decision.lifecycle",
                message=lifecycle_event,
            )
            if self.notification_bridge is not None:
                await self.notification_bridge.publish_strategy_event(lifecycle_event)

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

    async def _apply_planner_llm_suggestion(
        self,
        *,
        trace_id: str,
        decision_id: str,
        strategy: StrategyConfig,
        market_context: Mapping[str, Any],
        plan: Any,
    ) -> Any:
        if self.llm_runtime is None:
            return plan
        try:
            suggestion = await self.llm_runtime.suggest_plan(
                trace_id=trace_id,
                decision_id=decision_id,
                market_context=market_context,
                strategy=strategy,
                heuristic_plan=plan,
            )
        except Exception as exc:  # noqa: BLE001 - planner fallback must not break execution pipeline
            rationale = list(plan.rationale)
            rationale.append(f"llm_planner_fallback={exc.__class__.__name__}")
            return type(plan)(
                action=plan.action,
                confidence=plan.confidence,
                target_quantity=plan.target_quantity,
                rationale=tuple(rationale),
                metrics=dict(plan.metrics),
            )
        action = suggestion.action if suggestion.action in {"BUY", "SELL", "HOLD", "CLOSE"} else plan.action
        confidence = plan.confidence if suggestion.confidence is None else max(0.0, min(1.0, suggestion.confidence))
        target_quantity = (
            plan.target_quantity
            if suggestion.target_quantity is None
            else float(suggestion.target_quantity)
        )
        rationale = list(plan.rationale)
        rationale.extend(list(suggestion.rationale))
        provider = str(suggestion.metadata.get("provider", "")).strip()
        model = str(suggestion.metadata.get("model", "")).strip()
        if provider and model:
            rationale.append(f"llm_provider={provider}/{model}")
        return type(plan)(
            action=action,
            confidence=confidence,
            target_quantity=target_quantity,
            rationale=tuple(rationale),
            metrics=dict(plan.metrics),
        )

    async def _apply_risk_llm_suggestion(
        self,
        *,
        trace_id: str,
        decision_id: str,
        strategy: StrategyConfig,
        market_context: Mapping[str, Any],
        plan: Any,
        risk: Any,
    ) -> Any:
        if self.llm_runtime is None:
            return risk
        try:
            suggestion = await self.llm_runtime.suggest_risk(
                trace_id=trace_id,
                decision_id=decision_id,
                market_context=market_context,
                strategy=strategy,
                heuristic_risk=risk,
                heuristic_plan=plan,
            )
        except Exception as exc:  # noqa: BLE001 - risk fallback must not break execution pipeline
            rationale = list(risk.rationale)
            rationale.append(f"llm_risk_fallback={exc.__class__.__name__}")
            return type(risk)(
                approved=risk.approved,
                approved_quantity=risk.approved_quantity,
                signals=risk.signals,
                blocked_by=risk.blocked_by,
                risk_score=risk.risk_score,
                rationale=tuple(rationale),
            )
        approved = risk.approved if suggestion.approved is None else bool(suggestion.approved)
        approved_quantity = (
            risk.approved_quantity
            if suggestion.approved_quantity is None
            else float(suggestion.approved_quantity)
        )
        risk_score = risk.risk_score if suggestion.risk_score is None else max(0.0, min(1.0, suggestion.risk_score))
        blocked_by = risk.blocked_by if not suggestion.blocked_by else tuple(suggestion.blocked_by)
        rationale = list(risk.rationale)
        rationale.extend(list(suggestion.rationale))
        provider = str(suggestion.metadata.get("provider", "")).strip()
        model = str(suggestion.metadata.get("model", "")).strip()
        if provider and model:
            rationale.append(f"llm_provider={provider}/{model}")
        return type(risk)(
            approved=approved,
            approved_quantity=approved_quantity,
            signals=risk.signals,
            blocked_by=blocked_by,
            risk_score=risk_score,
            rationale=tuple(rationale),
        )

    async def _apply_execution_llm_suggestion(
        self,
        *,
        trace_id: str,
        decision_id: str,
        strategy: StrategyConfig,
        market_context: Mapping[str, Any],
        plan: Any,
        risk: Any,
        execution_decision: Any,
    ) -> Any:
        if self.llm_runtime is None:
            return execution_decision
        try:
            suggestion = await self.llm_runtime.suggest_execution(
                trace_id=trace_id,
                decision_id=decision_id,
                market_context=market_context,
                strategy=strategy,
                heuristic_execution=execution_decision,
                heuristic_plan=plan,
                heuristic_risk=risk,
            )
        except Exception as exc:  # noqa: BLE001 - execution fallback must not break execution pipeline
            rationale = list(execution_decision.rationale)
            rationale.append(f"llm_execution_fallback={exc.__class__.__name__}")
            return type(execution_decision)(
                action=execution_decision.action,
                quantity=execution_decision.quantity,
                confidence=execution_decision.confidence,
                rationale=tuple(rationale),
                constraints=dict(execution_decision.constraints),
            )
        action = (
            suggestion.action
            if suggestion.action in {"BUY", "SELL", "HOLD", "CLOSE"}
            else execution_decision.action
        )
        quantity = execution_decision.quantity if suggestion.quantity is None else float(suggestion.quantity)
        confidence = (
            execution_decision.confidence
            if suggestion.confidence is None
            else max(0.0, min(1.0, suggestion.confidence))
        )
        constraints = dict(execution_decision.constraints)
        constraints.update(dict(suggestion.constraints))
        rationale = list(execution_decision.rationale)
        rationale.extend(list(suggestion.rationale))
        provider = str(suggestion.metadata.get("provider", "")).strip()
        model = str(suggestion.metadata.get("model", "")).strip()
        if provider and model:
            rationale.append(f"llm_provider={provider}/{model}")
        return type(execution_decision)(
            action=action,
            quantity=quantity,
            confidence=confidence,
            rationale=tuple(rationale),
            constraints=constraints,
        )

    def _run_sync_stage(
        self,
        *,
        stage: str,
        trace_id: str,
        decision_id: str,
        mode: str,
        operation: Callable[[], Any],
    ) -> Any:
        started = self._monotonic_clock()
        try:
            result = operation()
        except Exception as exc:  # noqa: BLE001 - stage wrapper records all runtime failures
            self.metrics.record_stage_failure(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                latency_ms=(self._monotonic_clock() - started) * 1000.0,
                error_type=exc.__class__.__name__,
            )
            raise
        self.metrics.record_stage_success(
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            stage=stage,
            latency_ms=(self._monotonic_clock() - started) * 1000.0,
        )
        return result

    async def _run_async_stage(
        self,
        *,
        stage: str,
        trace_id: str,
        decision_id: str,
        mode: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        started = self._monotonic_clock()
        try:
            result = await operation()
        except Exception as exc:  # noqa: BLE001 - stage wrapper records all runtime failures
            self.metrics.record_stage_failure(
                trace_id=trace_id,
                decision_id=decision_id,
                mode=mode,
                stage=stage,
                latency_ms=(self._monotonic_clock() - started) * 1000.0,
                error_type=exc.__class__.__name__,
            )
            raise
        self.metrics.record_stage_success(
            trace_id=trace_id,
            decision_id=decision_id,
            mode=mode,
            stage=stage,
            latency_ms=(self._monotonic_clock() - started) * 1000.0,
        )
        return result
