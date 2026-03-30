#!/usr/bin/env python3
"""Generate a JWT signed with RS256 for the openTrader API.

Usage:
    python scripts/generate_token_rs256.py --user-id operator1 --role admin

Environment variables:
    JWT_PRIVATE_KEY   - PEM-encoded RSA private key (or use --key-file)
    JWT_ISSUER        - Token issuer (default: opentrader)
    JWT_AUDIENCE      - Token audience (default: opentrader-api)
"""

from __future__ import annotations

import argparse
import os
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an RS256-signed JWT")
    parser.add_argument("--user-id", required=True, help="Subject (user id) for the token")
    parser.add_argument(
        "--role", required=True, choices=["viewer", "operator", "admin"], help="Role claim"
    )
    parser.add_argument(
        "--key-file",
        default=None,
        help="Path to PEM private key file (overrides JWT_PRIVATE_KEY env)",
    )
    parser.add_argument(
        "--ttl", type=int, default=3600, help="Token TTL in seconds (default: 3600)"
    )
    args = parser.parse_args()

    # Auto-load .env if JWT_PRIVATE_KEY not in environment
    if not os.environ.get("JWT_PRIVATE_KEY"):
        try:
            from services.shared.runtime.env_loader import load_dotenv_file
            load_dotenv_file()
        except ImportError:
            # Manual .env loading as fallback
            env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
            if os.path.exists(env_path):
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if key and key not in os.environ:
                            os.environ[key] = value

    # Resolve private key
    private_key_pem: str | None = None
    if args.key_file:
        with open(args.key_file, "r", encoding="utf-8") as fh:
            private_key_pem = fh.read()
    else:
        private_key_pem = os.environ.get("JWT_PRIVATE_KEY")
        # Try file path if inline key not set
        if not private_key_pem:
            key_file = os.environ.get("JWT_PRIVATE_KEY_FILE", "").strip()
            if key_file and os.path.exists(key_file):
                with open(key_file, "r", encoding="utf-8") as fh:
                    private_key_pem = fh.read()

    if not private_key_pem:
        print(
            "error: no private key provided (set JWT_PRIVATE_KEY or use --key-file)",
            file=sys.stderr,
        )
        sys.exit(1)

    issuer = os.environ.get("JWT_ISSUER", "open-trader")
    audience = os.environ.get("JWT_AUDIENCE", "open-trader-api")

    try:
        import jwt
    except ImportError:
        print("error: PyJWT is required (pip install PyJWT)", file=sys.stderr)
        sys.exit(1)

    now = int(time.time())
    payload = {
        "sub": args.user_id,
        "role": args.role,
        "iat": now,
        "exp": now + args.ttl,
        "iss": issuer,
        "aud": audience,
    }

    token = jwt.encode(payload, private_key_pem, algorithm="RS256")
    print(token)


if __name__ == "__main__":
    main()
