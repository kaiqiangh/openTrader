# Continuous Learning v2 Notes - P5 Reconciliation, Position, and Portfolio Batch

Source session: `2026-02-14` (`P5-002`, `P5-003`, `P5-004`)

## Atomic Instincts

```yaml
---
id: reconcile-from-queue-events-then-fallback-to-exchange
trigger: "when maintaining OMS truth under delayed or missing fills"
confidence: 0.88
domain: "trade-lifecycle"
source: "session-observation"
---
action: "Prioritize queue lifecycle events, then apply exchange snapshot fallback only when status/fill completeness requires recovery."
evidence:
  - "`FillReconciliationEngine.reconcile()` merges queue events first and conditionally applies exchange snapshot fallback."
```

```yaml
---
id: position-engine-must-handle-reduce-close-and-flip-paths
trigger: "when applying signed fills to netted positions"
confidence: 0.89
domain: "trade-lifecycle"
source: "session-observation"
---
action: "Implement explicit logic for add/reduce/close/flip scenarios with deterministic realized-PnL and fee handling."
evidence:
  - "`PositionEngine.apply_fill()` computes direction-aware realized deltas and supports position flips with normalized status outputs."
```

```yaml
---
id: build-mode-tagged-portfolio-snapshots-from-marked-positions
trigger: "when publishing account health views to downstream risk and control planes"
confidence: 0.85
domain: "portfolio-management"
source: "session-observation"
---
action: "Calculate total/available/locked balances with unrealized and realized PnL while enforcing mode consistency and mark-price completeness."
evidence:
  - "`PortfolioSnapshotEngine.build_snapshot()` validates mode alignment, requires mark prices for open positions, and emits normalized snapshots."
```
