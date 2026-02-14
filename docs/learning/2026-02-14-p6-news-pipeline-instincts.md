# Continuous Learning v2 Notes - P6 News Pipeline Batch

Source session: `2026-02-14` (`P6-002`, `P6-003`, `P6-004`)

## Atomic Instincts

```yaml
---
id: normalize-news-items-before-dedupe-and-persist
trigger: "when ingesting heterogeneous source records"
confidence: 0.87
domain: "data-pipelines"
source: "session-observation"
---
action: "Convert incoming records into a strict normalized contract before dedupe and storage to keep downstream logic stable."
evidence:
  - "`NewsIngestionService` produces `NormalizedNewsItem` artifacts with validated required fields and canonical payload shape."
```

```yaml
---
id: dedupe-news-by-source-identity-and-content-hash
trigger: "when the same story can arrive via multiple channels"
confidence: 0.9
domain: "data-quality"
source: "session-observation"
---
action: "Apply layered dedupe checks using source identifiers plus content hash to collapse duplicates without dropping unique source items."
evidence:
  - "`NewsIngestionService.ingest()` checks `(source, source_item_id)` first, then `content_hash` before persistence."
```

```yaml
---
id: guarantee-summary-output-even-for-empty-or-unavailable-windows
trigger: "when summarization windows may have sparse inputs"
confidence: 0.86
domain: "resilience"
source: "session-observation"
---
action: "Always emit a deterministic summary artifact and use explicit fallback text when scoped inputs are empty."
evidence:
  - "`RollingNewsSummarizer.summarize_window()` returns `summary_text='news_unavailable'` when no scoped items are selected."
```
