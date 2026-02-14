from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from os import urandom

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION_PREFIX = "v1:"
_NONCE_BYTES = 12
_KEY_BYTES = 32
_AAD = b"open-trader:exchange-credentials:v1"


class KeyEncryptionError(ValueError):
    """Raised when key encryption/decryption fails."""


@dataclass(frozen=True, slots=True)
class AesGcmKeyEncryptor:
    """AES-256-GCM encryptor for exchange API credential persistence."""

    encryption_key_base64: str
    _key_bytes: bytes = field(init=False, repr=False)
    _cipher: AESGCM = field(init=False, repr=False)

    def __post_init__(self) -> None:
        key = _decode_base64(self.encryption_key_base64)
        if len(key) != _KEY_BYTES:
            raise KeyEncryptionError("ENCRYPTION_KEY_BASE64 must decode to exactly 32 bytes for AES-256-GCM")
        object.__setattr__(self, "_key_bytes", key)
        object.__setattr__(self, "_cipher", AESGCM(key))

    def encrypt(self, plaintext: str) -> str:
        if plaintext == "":
            raise KeyEncryptionError("plaintext must be non-empty")
        nonce = urandom(_NONCE_BYTES)
        ciphertext = self._cipher.encrypt(nonce, plaintext.encode("utf-8"), _AAD)
        payload = nonce + ciphertext
        return _VERSION_PREFIX + b64encode(payload).decode("utf-8")

    def decrypt(self, encrypted_payload: str) -> str:
        if not encrypted_payload.startswith(_VERSION_PREFIX):
            raise KeyEncryptionError("encrypted payload version is unsupported")
        encoded = encrypted_payload[len(_VERSION_PREFIX) :]
        raw = _decode_base64(encoded)
        if len(raw) <= _NONCE_BYTES:
            raise KeyEncryptionError("encrypted payload is malformed")

        nonce = raw[:_NONCE_BYTES]
        ciphertext = raw[_NONCE_BYTES:]
        try:
            plaintext = self._cipher.decrypt(nonce, ciphertext, _AAD)
        except Exception as exc:  # noqa: BLE001
            raise KeyEncryptionError("encrypted payload authentication failed") from exc
        return plaintext.decode("utf-8")


def _decode_base64(value: str) -> bytes:
    try:
        return b64decode(value, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise KeyEncryptionError("invalid base64-encoded encryption key/payload") from exc
