"""Security acceptance tests: weak credential defaults must fail."""

import os
import pytest


def test_rabbitmq_broker_rejects_missing_credentials():
    """Broker should raise RuntimeError when RABBITMQ credentials are not set."""
    old_user = os.environ.pop("RABBITMQ_DEFAULT_USER", None)
    old_pass = os.environ.pop("RABBITMQ_DEFAULT_PASS", None)
    try:
        from services.shared.runtime.rabbitmq_http_broker import RabbitMQHTTPTopicBroker

        with pytest.raises(RuntimeError, match="RABBITMQ_DEFAULT"):
            RabbitMQHTTPTopicBroker.from_env()
    finally:
        if old_user:
            os.environ["RABBITMQ_DEFAULT_USER"] = old_user
        if old_pass:
            os.environ["RABBITMQ_DEFAULT_PASS"] = old_pass


def test_database_rejects_missing_password():
    """Database config should raise RuntimeError when POSTGRES_PASSWORD is not set."""
    old_url = os.environ.pop("DATABASE_URL", None)
    old_pw = os.environ.pop("POSTGRES_PASSWORD", None)
    old_host = os.environ.pop("POSTGRES_HOST", None)
    old_db = os.environ.pop("POSTGRES_DB", None)
    old_user = os.environ.pop("POSTGRES_USER", None)
    try:
        from services.shared.runtime.database import load_runtime_database_settings

        with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
            load_runtime_database_settings()
    finally:
        if old_url:
            os.environ["DATABASE_URL"] = old_url
        if old_pw:
            os.environ["POSTGRES_PASSWORD"] = old_pw
        if old_host:
            os.environ["POSTGRES_HOST"] = old_host
        if old_db:
            os.environ["POSTGRES_DB"] = old_db
        if old_user:
            os.environ["POSTGRES_USER"] = old_user
