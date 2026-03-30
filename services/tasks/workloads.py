from services.tasks.celery_app import app


@app.task
def daily_portfolio_rollup():
    """Compute daily portfolio summary and persist."""
    # TODO: implement
    return {"status": "placeholder"}


@app.task
def news_backfill():
    """Backfill missing news articles from configured sources."""
    # TODO: implement
    return {"status": "placeholder"}


@app.task
def data_retention_cleanup():
    """Clean up old data per retention policy.

    Retention periods:
    - notification_events: 30 days
    - notification_deliveries: 30 days
    - llm_call_records: 90 days
    - agent_trace_spans: 90 days
    - portfolio_snapshots: 365 days
    """
    import os
    import logging
    from datetime import datetime, timezone, timedelta

    logger = logging.getLogger(__name__)

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
            "llm_call_records": now - timedelta(days=90),
            "agent_trace_spans": now - timedelta(days=90),
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
    """Generate and send notification digest."""
    # TODO: implement
    return {"status": "placeholder"}


@app.task
def replay_report():
    """Generate decision replay report."""
    # TODO: implement
    return {"status": "placeholder"}
