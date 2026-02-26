from __future__ import annotations

from dataclasses import dataclass
import os

from services.shared.runtime.env_loader import load_dotenv_file


@dataclass(frozen=True, slots=True)
class APISettings:
    app_name: str
    app_version: str
    default_mode: str
    jwt_secret_key: str
    jwt_issuer: str
    jwt_audience: str
    cors_allowed_origins: tuple[str, ...] = ()
    llm_runtime_enabled: bool = False
    litellm_base_url: str = ""
    llm_quick_provider_order: tuple[str, ...] = ()
    llm_deep_provider_order: tuple[str, ...] = ()
    read_only_mode: bool = False
    strict_database_mode: bool = True


def load_api_settings() -> APISettings:
    load_dotenv_file()
    default_mode = os.getenv("EXECUTION_MODE_DEFAULT", "MOCK").strip().upper() or "MOCK"
    if default_mode not in {"MOCK", "REAL"}:
        raise ValueError("EXECUTION_MODE_DEFAULT must be MOCK or REAL")

    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "").strip()
    if not jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY is required for API authentication")

    return APISettings(
        app_name=os.getenv("APP_NAME", "open-trader").strip() or "open-trader",
        app_version=os.getenv("APP_VERSION", "0.1.0").strip() or "0.1.0",
        default_mode=default_mode,
        jwt_secret_key=jwt_secret_key,
        jwt_issuer=os.getenv("JWT_ISSUER", "open-trader").strip() or "open-trader",
        jwt_audience=os.getenv("JWT_AUDIENCE", "open-trader-api").strip() or "open-trader-api",
        cors_allowed_origins=_parse_csv(
            os.getenv(
                "API_CORS_ALLOWED_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            )
        ),
        llm_runtime_enabled=_parse_bool(
            os.getenv("LLM_RUNTIME_ENABLED", "false"),
            setting_name="LLM_RUNTIME_ENABLED",
        ),
        litellm_base_url=os.getenv("LITELLM_BASE_URL", "").strip(),
        llm_quick_provider_order=_parse_csv(os.getenv("LLM_QUICK_PROVIDER_ORDER", "litellm")),
        llm_deep_provider_order=_parse_csv(os.getenv("LLM_DEEP_PROVIDER_ORDER", "litellm")),
        read_only_mode=_parse_bool(os.getenv("API_READ_ONLY_MODE", "false"), setting_name="API_READ_ONLY_MODE"),
        strict_database_mode=_parse_bool(
            os.getenv("API_STRICT_DATABASE_MODE", "true"),
            setting_name="API_STRICT_DATABASE_MODE",
        ),
    )


def _parse_bool(value: str, *, setting_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{setting_name} must be a boolean value")


def _parse_csv(value: str) -> tuple[str, ...]:
    tokens = tuple(item.strip() for item in value.split(",") if item.strip())
    return tokens
