# Continuous Learning v2 Notes - P1 Agent Trace Schema Batch

Source session: `2026-02-14` (`P1-005`)

## Atomic Instincts

```yaml
---
id: model-agent-traces-as-linked-decision-run-message-tables
trigger: "when adding replay/audit persistence for agent workflows"
confidence: 0.86
domain: "database-design"
source: "session-observation"
---
action: "Separate decision traces, agent runs, and agent messages into normalized tables with explicit foreign-key links."
evidence:
  - "`20260214_0003_agent_trace_schema.py` creates `decision_traces`, `agent_runs`, and `agent_messages` with FK chains."
```

```yaml
---
id: optimize-trace-schema-for-query-paths-immediately
trigger: "when new persistence tables will power replay and diagnostics"
confidence: 0.84
domain: "database-performance"
source: "session-observation"
---
action: "Add indexes for expected read paths during initial migration instead of deferring until after production load."
evidence:
  - "Agent trace migration defines `idx_agent_runs_decision_id` and `idx_agent_messages_agent_run_id_created_at`."
```

```yaml
---
id: gate-migrations-with-structure-tests
trigger: "when introducing schema migrations in fast-moving phases"
confidence: 0.82
domain: "integration-testing"
source: "session-observation"
---
action: "Write tests asserting migration file presence plus required table/index tokens before applying docs/status updates."
evidence:
  - "`tests/test_phase1_agent_trace_migration.py` enforces table and index contract strings for migration safety."
```
