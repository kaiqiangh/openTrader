from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from services.oms import PortfolioSnapshot, PositionState, ReconciliationOrder, RiskControlEvent, RiskControlPlane

_VALID_MODES = {"MOCK", "REAL"}
_VALID_STATES = {"ENABLED", "DISABLED", "PAUSED"}


@dataclass(frozen=True, slots=True)
class StrategyRuntimeRecord:
    strategy_id: str
    symbol: str
    mode: str
    state: str
    updated_at: str
    changed_by: str
    reason: str | None


@dataclass(slots=True)
class ControlPlaneState:
    mode: str
    strategies: dict[str, StrategyRuntimeRecord] = field(default_factory=dict)
    orders: list[ReconciliationOrder] = field(default_factory=list)
    positions: list[PositionState] = field(default_factory=list)
    portfolio_snapshots: list[PortfolioSnapshot] = field(default_factory=list)
    risk_controls: RiskControlPlane = field(default_factory=RiskControlPlane)
    risk_events: list[RiskControlEvent] = field(default_factory=list)

    def set_mode(self, *, mode: str, actor: str, reason: str) -> tuple[bool, str]:
        normalized_mode = _normalize_mode(mode)
        changed = normalized_mode != self.mode
        self.mode = normalized_mode

        if not changed:
            return False, _utc_now_iso()

        now = _utc_now_iso()
        self.strategies = {
            strategy_id: StrategyRuntimeRecord(
                strategy_id=record.strategy_id,
                symbol=record.symbol,
                mode=normalized_mode,
                state=record.state,
                updated_at=now,
                changed_by=actor,
                reason=reason,
            )
            for strategy_id, record in self.strategies.items()
        }
        return True, now

    def list_strategies(self) -> tuple[StrategyRuntimeRecord, ...]:
        return tuple(self.strategies[key] for key in sorted(self.strategies.keys()))

    def set_strategy_state(
        self,
        *,
        strategy_id: str,
        state: str,
        actor: str,
        reason: str,
    ) -> StrategyRuntimeRecord:
        normalized_state = _normalize_strategy_state(state)
        key = strategy_id.strip()
        if not key:
            raise ValueError("strategy_id must be non-empty")

        existing = self.strategies.get(key)
        symbol = existing.symbol if existing is not None else _default_symbol(strategy_id=key)
        updated = StrategyRuntimeRecord(
            strategy_id=key,
            symbol=symbol,
            mode=self.mode,
            state=normalized_state,
            updated_at=_utc_now_iso(),
            changed_by=actor,
            reason=reason,
        )
        self.strategies[key] = updated
        return updated

    def list_orders(self, *, status: str | None = None, mode: str | None = None) -> tuple[ReconciliationOrder, ...]:
        status_filter = status.strip().upper() if status else None
        mode_filter = mode.strip().upper() if mode else None
        items: list[ReconciliationOrder] = []
        for order in self.orders:
            if status_filter and order.status.strip().upper() != status_filter:
                continue
            if mode_filter and order.mode.strip().upper() != mode_filter:
                continue
            items.append(order)
        return tuple(items)

    def list_positions(self, *, mode: str | None = None, symbol: str | None = None) -> tuple[PositionState, ...]:
        mode_filter = mode.strip().upper() if mode else None
        symbol_filter = symbol.strip().upper() if symbol else None
        items: list[PositionState] = []
        for position in self.positions:
            if mode_filter and position.mode.strip().upper() != mode_filter:
                continue
            if symbol_filter and position.symbol.strip().upper() != symbol_filter:
                continue
            items.append(position)
        return tuple(items)

    def latest_snapshot(self, *, mode: str | None = None) -> PortfolioSnapshot | None:
        if mode is None:
            candidates = self.portfolio_snapshots
        else:
            target_mode = mode.strip().upper()
            candidates = [snapshot for snapshot in self.portfolio_snapshots if snapshot.mode.strip().upper() == target_mode]

        if not candidates:
            return None

        return max(candidates, key=lambda snapshot: snapshot.snapshot_time)

    def risk_status(self) -> tuple[dict[str, object], tuple[RiskControlEvent, ...]]:
        snapshot = self.risk_controls.snapshot()
        gate = self.risk_controls.evaluate_order_allowed()
        recent = self._capture_risk_events()
        return (
            {
                "kill_switch_enabled": snapshot.kill_switch_enabled,
                "circuit_breaker_open": snapshot.circuit_breaker_open,
                "consecutive_failures": snapshot.consecutive_failures,
                "circuit_breaker_open_until": snapshot.circuit_breaker_open_until,
                "blocked_by": list(gate.blocked_by),
            },
            recent,
        )

    def trip_circuit_breaker(
        self,
        *,
        reason: str,
        actor: str,
        cooldown_seconds: int | None = None,
    ) -> RiskControlEvent:
        self.risk_controls.trip_circuit_breaker(reason=reason, actor=actor, cooldown_seconds=cooldown_seconds)
        return self._last_risk_event()

    def reset_circuit_breaker(self, *, reason: str, actor: str) -> RiskControlEvent:
        self.risk_controls.reset_circuit_breaker(reason=reason, actor=actor)
        return self._last_risk_event()

    def enable_kill_switch(self, *, reason: str, actor: str) -> RiskControlEvent:
        self.risk_controls.enable_kill_switch(reason=reason, actor=actor)
        return self._last_risk_event()

    def disable_kill_switch(self, *, reason: str, actor: str) -> RiskControlEvent:
        self.risk_controls.disable_kill_switch(reason=reason, actor=actor)
        return self._last_risk_event()

    def _last_risk_event(self) -> RiskControlEvent:
        events = self._capture_risk_events()
        if not events:
            raise RuntimeError("risk control action did not emit an event")
        return events[-1]

    def _capture_risk_events(self) -> tuple[RiskControlEvent, ...]:
        drained = self.risk_controls.drain_events()
        if drained:
            self.risk_events.extend(drained)
        return drained


def build_default_state(*, default_mode: str) -> ControlPlaneState:
    normalized_mode = _normalize_mode(default_mode)
    now = _utc_now_iso()
    strategies = {
        "btc-momentum": StrategyRuntimeRecord(
            strategy_id="btc-momentum",
            symbol="BTC/USDT",
            mode=normalized_mode,
            state="ENABLED",
            updated_at=now,
            changed_by="system",
            reason="bootstrap",
        ),
        "eth-mean-revert": StrategyRuntimeRecord(
            strategy_id="eth-mean-revert",
            symbol="ETH/USDT",
            mode=normalized_mode,
            state="ENABLED",
            updated_at=now,
            changed_by="system",
            reason="bootstrap",
        ),
    }
    return ControlPlaneState(mode=normalized_mode, strategies=strategies)


def _normalize_mode(mode: str) -> str:
    normalized_mode = mode.strip().upper()
    if normalized_mode not in _VALID_MODES:
        raise ValueError("mode must be MOCK or REAL")
    return normalized_mode


def _normalize_strategy_state(state: str) -> str:
    normalized_state = state.strip().upper()
    if normalized_state not in _VALID_STATES:
        raise ValueError("strategy state must be ENABLED, DISABLED, or PAUSED")
    return normalized_state


def _default_symbol(*, strategy_id: str) -> str:
    lowered = strategy_id.lower()
    if "eth" in lowered:
        return "ETH/USDT"
    return "BTC/USDT"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
