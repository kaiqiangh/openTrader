from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class APISettings:
    app_name: str
    app_version: str
    default_mode: str
    jwt_secret_key: str
    jwt_issuer: str
    jwt_audience: str


def load_api_settings() -> APISettings:
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
    )
