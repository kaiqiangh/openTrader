# Redis Namespace Strategy

This document defines the Phase 1 Redis keyspace conventions for short-term memory, hot snapshots, rate limits, and distributed locks.

Machine-readable source of truth:

- `config/redis/namespaces.json`

## Key Design Rules

1. Prefix keys by namespace (`mem`, `snapshot`, `rate`, `lock`) to keep scans scoped.
2. Include `mode` (`MOCK` or `REAL`) where decisions or execution state can leak between modes.
3. Require explicit TTL on all operational keys to avoid unbounded growth.
4. Reserve suffix placeholders (`{strategy_id}`, `{decision_id}`, `{agent_name}`) for deterministic lookups.

## Namespace Table

| Name              | Key Pattern                                                   | TTL (seconds) | Notes                                  |
| ----------------- | ------------------------------------------------------------- | ------------- | -------------------------------------- |
| `memory.decision` | `mem:decision:{mode}:{strategy_id}:{decision_id}:{slot}`      | 900           | Intra-cycle agent context and outputs. |
| `snapshot.market` | `snapshot:market:{exchange}:{symbol}:{interval}`             | 120           | Fresh market snapshots.                |
| `rate_limit`      | `rate:llm:{strategy_id}:{agent_name}:{window}`               | 90000         | Request/token quota counters.          |
| `lock`            | `lock:{resource}:{mode}`                                     | 30            | Lightweight distributed mutex keys.    |

## Operational Guidance

- Keep lock values unique per owner token and release only by token match.
- Refresh `memory.decision` keys only during the active decision cycle.
- Keep `snapshot.market` short-lived; stale snapshots must be treated as invalid inputs.
- For daily windows in `rate_limit`, use UTC-normalized window labels (`YYYY-MM-DD`).
