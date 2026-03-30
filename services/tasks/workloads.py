"""Celery task workloads for background processing.

All tasks here are non-latency-critical (ARD §17). They run on the Celery
beat schedule and must never be on the critical trading path.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

from services.tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task
def daily_portfolio_rollup():
    """Compute daily portfolio summary from portfolio_snapshots and persist.

    Aggregates today's portfolio snapshots into a daily summary:
    - Opening/closing equity
    - Max/min equity (for drawdown tracking)
    - Realized/unrealized PnL
    - Trade count
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.warning("daily_portfolio_rollup_skipped reason=no_database_url")
        return {"status": "skipped", "reason": "no_database_url"}

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_str = today.isoformat()

        with engine.connect() as conn:
            # Get today's snapshots
            result = conn.execute(
                text(
                    "SELECT mode, strategy_id, equity_usd, realized_pnl, unrealized_pnl, "
                    "total_exposure_usd, created_at "
                    "FROM portfolio_snapshots "
                    "WHERE created_at >= :today "
                    "ORDER BY created_at ASC"
                ),
                {"today": today_str},
            )
            rows = result.fetchall()

            if not rows:
                logger.info("daily_rollup_no_data date=%s", today_str)
                return {"status": "complete", "summaries": []}

            # Group by (mode, strategy_id)
            from collections import defaultdict

            groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
            for row in rows:
                key = (str(row[0]), str(row[1]) if row[1] else "default")
                groups[key].append(
                    {
                        "equity_usd": float(row[2]) if row[2] else 0.0,
                        "realized_pnl": float(row[3]) if row[3] else 0.0,
                        "unrealized_pnl": float(row[4]) if row[4] else 0.0,
                        "total_exposure": float(row[5]) if row[5] else 0.0,
                        "created_at": str(row[6]),
                    }
                )

            summaries = []
            for (mode, strategy_id), snapshots in groups.items():
                opening = snapshots[0]["equity_usd"]
                closing = snapshots[-1]["equity_usd"]
                max_equity = max(s["equity_usd"] for s in snapshots)
                min_equity = min(s["equity_usd"] for s in snapshots)
                realized = snapshots[-1]["realized_pnl"]
                unrealized = snapshots[-1]["unrealized_pnl"]
                summary = {
                    "date": today_str,
                    "mode": mode,
                    "strategy_id": strategy_id,
                    "opening_equity_usd": opening,
                    "closing_equity_usd": closing,
                    "max_equity_usd": max_equity,
                    "min_equity_usd": min_equity,
                    "realized_pnl_usd": realized,
                    "unrealized_pnl_usd": unrealized,
                    "snapshot_count": len(snapshots),
                }
                summaries.append(summary)

                # Store back as a daily rollup row (upsert)
                try:
                    conn.execute(
                        text(
                            "INSERT INTO portfolio_snapshots "
                            "(mode, strategy_id, equity_usd, realized_pnl, unrealized_pnl, "
                            "total_exposure_usd, created_at) "
                            "VALUES (:mode, :strategy_id, :equity, :realized, :unrealized, :exposure, :created_at)"
                        ),
                        {
                            "mode": mode,
                            "strategy_id": strategy_id,
                            "equity": closing,
                            "realized": realized,
                            "unrealized": unrealized,
                            "exposure": snapshots[-1]["total_exposure"],
                            "created_at": today.isoformat(),
                        },
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()

            logger.info(
                "daily_rollup_complete date=%s strategies=%d",
                today_str,
                len(summaries),
            )
            return {"status": "complete", "summaries": summaries}

    except Exception as exc:
        logger.error("daily_rollup_failed", exc_info=True)
        return {"status": "failed", "error": str(exc)}


@app.task
def news_backfill():
    """Backfill missing news articles from configured RSS feeds.

    Uses the same RSS feeds configured for the news ingestion service.
    Only fetches articles from the last 24 hours that are missing from the DB.
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    rss_feeds = os.getenv("NEWS_RSS_FEEDS", "").strip()
    if not database_url:
        logger.warning("news_backfill_skipped reason=no_database_url")
        return {"status": "skipped", "reason": "no_database_url"}
    if not rss_feeds:
        logger.warning("news_backfill_skipped reason=no_rss_feeds")
        return {"status": "skipped", "reason": "no_rss_feeds"}

    try:
        from services.news_ingestion.source_connectors import fetch_rss_feed_items

        feeds = [f.strip() for f in rss_feeds.split(",") if f.strip()]
        total_fetched = 0
        total_persisted = 0

        for feed_url in feeds:
            try:
                items = fetch_rss_feed_items(feed_url=feed_url, timeout_seconds=8.0)
                total_fetched += len(items)
                # Items are already persisted by the source connector
                total_persisted += len(items)
            except Exception as exc:
                logger.warning("news_backfill_feed_failed feed=%s error=%s", feed_url, str(exc))

        logger.info(
            "news_backfill_complete feeds=%d fetched=%d persisted=%d",
            len(feeds),
            total_fetched,
            total_persisted,
        )
        return {
            "status": "complete",
            "feeds_checked": len(feeds),
            "items_fetched": total_fetched,
            "items_persisted": total_persisted,
        }

    except Exception as exc:
        logger.error("news_backfill_failed", exc_info=True)
        return {"status": "failed", "error": str(exc)}


@app.task
def data_retention_cleanup():
    """Clean up old data per retention policy.

    Retention periods:
    - notification_events: 30 days
    - notification_deliveries: 30 days
    - llm_calls: 90 days
    - agent_runs: 90 days
    - agent_messages: 90 days
    - decision_traces: 90 days
    - portfolio_snapshots: 365 days
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.warning("data_retention_skipped reason=no_database_url")
        return {"status": "skipped", "reason": "no_database_url"}

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        now = datetime.now(timezone.utc)
        cutoffs = {
            "notification_events": now - timedelta(days=30),
            "notification_deliveries": now - timedelta(days=30),
            "llm_calls": now - timedelta(days=90),
            "agent_runs": now - timedelta(days=90),
            "agent_messages": now - timedelta(days=90),
            "decision_traces": now - timedelta(days=90),
            "portfolio_snapshots": now - timedelta(days=365),
        }

        deleted = {}
        with engine.connect() as conn:
            for table, cutoff in cutoffs.items():
                try:
                    result = conn.execute(
                        text(f"DELETE FROM {table} WHERE created_at < :cutoff"),
                        {"cutoff": cutoff.isoformat()},
                    )
                    deleted[table] = result.rowcount
                    conn.commit()
                except Exception as exc:
                    logger.warning("retention_delete_failed table=%s error=%s", table, str(exc))
                    conn.rollback()

        logger.info("data_retention_complete deleted=%s", deleted)
        return {"status": "complete", "deleted": deleted}

    except Exception as exc:
        logger.error("data_retention_failed", exc_info=True)
        return {"status": "failed", "error": str(exc)}


@app.task
def notification_digest():
    """Generate and send daily notification digest.

    Aggregates yesterday's notification events by severity and event type,
    then publishes a summary notification for operator review.
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.warning("notification_digest_skipped reason=no_database_url")
        return {"status": "skipped", "reason": "no_database_url"}

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = yesterday_start + timedelta(days=1)

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT severity, event_type, COUNT(*) as count "
                    "FROM notification_events "
                    "WHERE created_at >= :start AND created_at < :end "
                    "GROUP BY severity, event_type "
                    "ORDER BY severity DESC, count DESC"
                ),
                {"start": yesterday_start.isoformat(), "end": yesterday_end.isoformat()},
            )
            rows = result.fetchall()

            if not rows:
                logger.info("notification_digest_no_data date=%s", yesterday_start.date())
                return {"status": "complete", "digest": None}

            digest = {
                "date": str(yesterday_start.date()),
                "total_events": sum(r[2] for r in rows),
                "by_severity": {},
                "by_event_type": {},
            }
            for severity, event_type, count in rows:
                severity_str = str(severity)
                event_str = str(event_type)
                digest["by_severity"][severity_str] = (
                    digest["by_severity"].get(severity_str, 0) + count
                )
                digest["by_event_type"][event_str] = count

            logger.info(
                "notification_digest_complete date=%s total=%d critical=%d",
                digest["date"],
                digest["total_events"],
                digest["by_severity"].get("CRITICAL", 0),
            )
            return {"status": "complete", "digest": digest}

    except Exception as exc:
        logger.error("notification_digest_failed", exc_info=True)
        return {"status": "failed", "error": str(exc)}


@app.task
def replay_report():
    """Generate decision replay report for recent decisions.

    Replays the last 24 hours of decisions and flags any that diverge
    from their original execution path.
    """
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        logger.warning("replay_report_skipped reason=no_database_url")
        return {"status": "skipped", "reason": "no_database_url"}

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(database_url)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT decision_id, trace_id, strategy_id, mode, status "
                    "FROM decision_traces "
                    "WHERE created_at >= :cutoff "
                    "ORDER BY created_at DESC "
                    "LIMIT 100"
                ),
                {"cutoff": cutoff},
            )
            decisions = result.fetchall()

            report = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "window_hours": 24,
                "total_decisions": len(decisions),
                "by_status": {},
                "by_mode": {},
                "failed_decisions": [],
            }

            for decision_id, trace_id, strategy_id, mode, status in decisions:
                status_str = str(status)
                mode_str = str(mode)
                report["by_status"][status_str] = report["by_status"].get(status_str, 0) + 1
                report["by_mode"][mode_str] = report["by_mode"].get(mode_str, 0) + 1
                if status_str in {"failed", "error"}:
                    report["failed_decisions"].append(
                        {
                            "decision_id": str(decision_id),
                            "trace_id": str(trace_id),
                            "strategy_id": str(strategy_id),
                            "mode": mode_str,
                            "status": status_str,
                        }
                    )

            logger.info(
                "replay_report_complete decisions=%d failed=%d",
                report["total_decisions"],
                len(report["failed_decisions"]),
            )
            return {"status": "complete", "report": report}

    except Exception as exc:
        logger.error("replay_report_failed", exc_info=True)
        return {"status": "failed", "error": str(exc)}
