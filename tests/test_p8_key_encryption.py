from __future__ import annotations

from base64 import b64encode
import os
import sqlite3

import pytest

from services.shared.runtime.exchange_credentials import EncryptedExchangeCredentialStore
from services.shared.runtime.key_encryption import AesGcmKeyEncryptor, KeyEncryptionError


def _valid_key_base64() -> str:
    return b64encode(os.urandom(32)).decode("utf-8")


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE exchanges (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            api_key_encrypted TEXT,
            api_secret_encrypted TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def test_aes_gcm_encryptor_round_trip() -> None:
    encryptor = AesGcmKeyEncryptor(encryption_key_base64=_valid_key_base64())
    ciphertext = encryptor.encrypt("api-key-raw-value")
    assert ciphertext != "api-key-raw-value"
    assert encryptor.decrypt(ciphertext) == "api-key-raw-value"


def test_aes_gcm_encryptor_rejects_invalid_key_length() -> None:
    invalid_key = b64encode(os.urandom(16)).decode("utf-8")
    with pytest.raises(KeyEncryptionError):
        AesGcmKeyEncryptor(encryption_key_base64=invalid_key)


def test_aes_gcm_encryptor_detects_tampered_ciphertext() -> None:
    encryptor = AesGcmKeyEncryptor(encryption_key_base64=_valid_key_base64())
    ciphertext = encryptor.encrypt("super-secret")
    tampered = ciphertext[:-4] + "ABCD"
    with pytest.raises(KeyEncryptionError):
        encryptor.decrypt(tampered)


def test_encrypted_exchange_credential_store_persists_only_ciphertext() -> None:
    connection = _connection()
    store = EncryptedExchangeCredentialStore(
        connection=connection,
        encryptor=AesGcmKeyEncryptor(encryption_key_base64=_valid_key_base64()),
    )

    store.upsert_credentials(
        exchange_name="binance",
        api_key="raw-api-key",
        api_secret="raw-api-secret",
    )

    row = connection.execute(
        "SELECT api_key_encrypted, api_secret_encrypted FROM exchanges WHERE name = ?",
        ("binance",),
    ).fetchone()
    assert row is not None
    assert "raw-api-key" not in str(row["api_key_encrypted"])
    assert "raw-api-secret" not in str(row["api_secret_encrypted"])

    loaded = store.load_credentials(exchange_name="binance")
    assert loaded is not None
    assert loaded.api_key == "raw-api-key"
    assert loaded.api_secret == "raw-api-secret"

