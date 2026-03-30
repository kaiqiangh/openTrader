"""Security acceptance tests: weak credential defaults must fail."""

import pytest
from unittest.mock import patch


def test_rabbitmq_broker_rejects_missing_credentials():
    """Broker should raise RuntimeError when RABBITMQ credentials are not set."""
    from services.shared.runtime.rabbitmq_http_broker import RabbitMQHTTPTopicBroker

    with patch("services.shared.runtime.rabbitmq_http_broker.load_dotenv_file"):
        with patch.dict("os.environ", {"RABBITMQ_DEFAULT_USER": "", "RABBITMQ_DEFAULT_PASS": ""}, clear=False):
            with pytest.raises(RuntimeError, match="RABBITMQ_DEFAULT"):
                RabbitMQHTTPTopicBroker.from_env()


def test_database_rejects_missing_password():
    """Database config should raise RuntimeError when POSTGRES_PASSWORD is not set."""
    from services.shared.runtime.database import load_runtime_database_settings

    with patch("services.shared.runtime.database.load_dotenv_file"):
        # Pass env directly to bypass os.environ
        with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
            load_runtime_database_settings(env={
                "DATABASE_URL": "",
                "POSTGRES_PASSWORD": "",
                "POSTGRES_HOST": "localhost",
                "POSTGRES_DB": "test",
                "POSTGRES_USER": "test",
            })
