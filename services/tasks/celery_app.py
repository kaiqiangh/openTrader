from celery import Celery
import os

app = Celery(
    "open_trader",
    broker=os.getenv("REDIS_URL", "redis://redis:6379/1"),
    backend=os.getenv("REDIS_URL", "redis://redis:6379/1"),
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "daily-portfolio-rollup": {
            "task": "services.tasks.workloads.daily_portfolio_rollup",
            "schedule": 86400.0,  # Daily
        },
        "news-backfill": {
            "task": "services.tasks.workloads.news_backfill",
            "schedule": 3600.0,  # Hourly
        },
        "data-retention-cleanup": {
            "task": "services.tasks.workloads.data_retention_cleanup",
            "schedule": 86400.0,  # Daily
        },
    },
)
