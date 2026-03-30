from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from services.oms.portfolio_snapshot import PortfolioSnapshot
from services.oms.position_engine import PositionState
from services.oms.risk_controls import RiskControlEvent, RiskControlGate, RiskControlPlane
from services.oms.risk_guards import (
    DrawdownDailyLossConfig,
    DrawdownDailyLossEvaluation,
    DrawdownDailyLossGuardEngine,
)
from services.oms.risk_rules import (
    CoreRiskConfig,
    CoreRiskEvaluation,
    CoreRiskRuleEngine,
    ProposedOrder,
)


@dataclass(frozen=True, slots=True)
class RiskPolicyConfig:
    core: CoreRiskConfig
    guards: DrawdownDailyLossConfig


@dataclass(frozen=True, slots=True)
class RiskPolicyDecision:
    allowed: bool
    blocked_by: tuple[str, ...]
    core: CoreRiskEvaluation
    guards: DrawdownDailyLossEvaluation
    controls: RiskControlGate


class RiskObservabilitySink(Protocol):
    def record_policy_decision(
        self,
        *,
        trace_id: str | None,
        decision_id: str | None,
        strategy_id: str | None,
        order: ProposedOrder,
        decision: RiskPolicyDecision,
    ) -> None: ...

    def record_control_events(self, *, events: tuple[RiskControlEvent, ...]) -> None: ...


class RiskPolicyEngine:
    """Composes OMS core rules, portfolio guards, and emergency controls."""

    def __init__(
        self,
        *,
        config: RiskPolicyConfig,
        controls: RiskControlPlane | None = None,
        observability_sink: RiskObservabilitySink | None = None,
    ) -> None:
        self._config = config
        self._core = CoreRiskRuleEngine(config=config.core)
        self._guards = DrawdownDailyLossGuardEngine(config=config.guards)
        self._controls = controls or RiskControlPlane()
        self._observability = observability_sink

    @property
    def controls(self) -> RiskControlPlane:
        return self._controls

    def evaluate(
        self,
        *,
        order: ProposedOrder,
        current_position: PositionState | None,
        snapshot: PortfolioSnapshot,
        peak_equity_usd: float,
        current_total_exposure_usd: float,
        now: datetime | None = None,
        trace_id: str | None = None,
        decision_id: str | None = None,
        strategy_id: str | None = None,
    ) -> RiskPolicyDecision:
        core = self._core.evaluate(
            order=order,
            current_position=current_position,
            account_equity_usd=float(snapshot.total_balance_usd),
            current_total_exposure_usd=current_total_exposure_usd,
        )
        guards = self._guards.evaluate(snapshot=snapshot, peak_equity_usd=peak_equity_usd)
        controls = self._controls.evaluate_order_allowed(now=now)

        blocked_by = _merge_blocked(core=core, guards=guards, controls=controls)
        decision = RiskPolicyDecision(
            allowed=not blocked_by,
            blocked_by=blocked_by,
            core=core,
            guards=guards,
            controls=controls,
        )
        if self._observability is not None:
            self._observability.record_policy_decision(
                trace_id=trace_id,
                decision_id=decision_id,
                strategy_id=strategy_id,
                order=order,
                decision=decision,
            )
        return decision

    def drain_control_events(self) -> tuple[RiskControlEvent, ...]:
        events = self._controls.drain_events()
        if self._observability is not None:
            self._observability.record_control_events(events=events)
        return events


def _merge_blocked(
    *,
    core: CoreRiskEvaluation,
    guards: DrawdownDailyLossEvaluation,
    controls: RiskControlGate,
) -> tuple[str, ...]:
    merged: list[str] = []
    for name in (*core.blocked_by, *guards.blocked_by, *controls.blocked_by):
        if name in merged:
            continue
        merged.append(name)
    return tuple(merged)
