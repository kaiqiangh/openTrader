from __future__ import annotations

from base64 import b64encode
import os

import pytest

from services.shared.runtime.key_encryption import AesGcmKeyEncryptor, KeyEncryptionError


def _valid_key_base64() -> str:
    return b64encode(os.urandom(32)).decode("utf-8")


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




