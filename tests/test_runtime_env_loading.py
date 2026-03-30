from __future__ import annotations

from services.api.settings import load_api_settings
from services.notification_service.settings import load_notification_worker_settings


def test_api_settings_loads_jwt_secret_from_dotenv(tmp_path, monkeypatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text("JWT_SECRET_KEY=dotenv-secret\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("EXECUTION_MODE_DEFAULT", raising=False)

    settings = load_api_settings()

    assert settings.jwt_secret_key == "dotenv-secret"
    assert settings.default_mode == "MOCK"
    assert settings.llm_quick_provider_order == ("default",)
    assert settings.llm_deep_provider_order == ("default",)


def test_notification_settings_loads_telegram_secrets_from_dotenv(tmp_path, monkeypatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "TELEGRAM_BOT_TOKEN=bot-from-dotenv\n"
        "TELEGRAM_DEFAULT_CHAT_ID=chat-from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_DEFAULT_CHAT_ID", raising=False)
    monkeypatch.delenv("NOTIFY_DEFAULT_GATEWAY", raising=False)

    settings = load_notification_worker_settings()

    assert settings.telegram_bot_token == "bot-from-dotenv"
    assert settings.telegram_default_chat_id == "chat-from-dotenv"
