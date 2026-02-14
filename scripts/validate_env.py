from __future__ import annotations

import os

REQUIRED_KEYS = [
    "APP_ENV",
    "APP_NAME",
    "LOG_LEVEL",
    "API_HOST",
    "API_PORT",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "REDIS_URL",
    "RABBITMQ_URL",
    "RABBITMQ_DEFAULT_USER",
    "RABBITMQ_DEFAULT_PASS",
    "EXECUTION_MODE_DEFAULT",
    "SIMULATION_SLIPPAGE_BPS",
    "SIMULATION_FEE_BPS",
    "ENCRYPTION_KEY_BASE64",
    "JWT_SECRET_KEY",
]


def main() -> int:
    missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
    if missing:
        print(f"Missing required env keys: {', '.join(missing)}")
        return 1
    print("Environment validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
