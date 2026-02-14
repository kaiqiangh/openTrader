from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import uuid

from services.shared.runtime.key_encryption import AesGcmKeyEncryptor


@dataclass(frozen=True, slots=True)
class ExchangeCredentials:
    exchange_name: str
    api_key: str
    api_secret: str


class EncryptedExchangeCredentialStore:
    """SQLite-backed encrypted exchange credential storage boundary."""

    def __init__(self, *, connection: sqlite3.Connection, encryptor: AesGcmKeyEncryptor) -> None:
        self.connection = connection
        self.encryptor = encryptor

    def upsert_credentials(self, *, exchange_name: str, api_key: str, api_secret: str) -> None:
        normalized = exchange_name.strip().lower()
        if not normalized:
            raise ValueError("exchange_name must be non-empty")
        if not api_key:
            raise ValueError("api_key must be non-empty")
        if not api_secret:
            raise ValueError("api_secret must be non-empty")

        encrypted_key = self.encryptor.encrypt(api_key)
        encrypted_secret = self.encryptor.encrypt(api_secret)

        self.connection.execute(
            """
            INSERT INTO exchanges (id, name, api_key_encrypted, api_secret_encrypted, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(name) DO UPDATE SET
                api_key_encrypted = excluded.api_key_encrypted,
                api_secret_encrypted = excluded.api_secret_encrypted,
                is_active = 1
            """,
            (str(uuid.uuid4()), normalized, encrypted_key, encrypted_secret),
        )
        self.connection.commit()

    def load_credentials(self, *, exchange_name: str) -> ExchangeCredentials | None:
        normalized = exchange_name.strip().lower()
        if not normalized:
            raise ValueError("exchange_name must be non-empty")
        row = self.connection.execute(
            """
            SELECT name, api_key_encrypted, api_secret_encrypted
            FROM exchanges
            WHERE name = ?
            """,
            (normalized,),
        ).fetchone()
        if row is None:
            return None

        encrypted_key = str(row["api_key_encrypted"] or "")
        encrypted_secret = str(row["api_secret_encrypted"] or "")
        if not encrypted_key or not encrypted_secret:
            return None

        return ExchangeCredentials(
            exchange_name=str(row["name"]),
            api_key=self.encryptor.decrypt(encrypted_key),
            api_secret=self.encryptor.decrypt(encrypted_secret),
        )

