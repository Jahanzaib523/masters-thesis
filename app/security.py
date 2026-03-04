"""
Security helpers for encryption-related operations.

This module encrypts sensitive data at rest using Fernet (symmetric encryption)
from the `cryptography` library.

Required configuration:
- `SAS_ENCRYPTION_KEY` in your environment / `.env`
  (generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
"""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


@lru_cache
def _get_fernet() -> Fernet:
    if not settings.sas_encryption_key:
        raise RuntimeError(
            "SAS_ENCRYPTION_KEY is not configured. "
            "Set it in your environment or .env to enable encryption at rest."
        )
    return Fernet(settings.sas_encryption_key.encode("utf-8"))


def encrypt_bytes(raw: bytes) -> bytes:
    return _get_fernet().encrypt(raw)


def decrypt_bytes(ciphertext: bytes) -> bytes:
    try:
        return _get_fernet().decrypt(ciphertext)
    except InvalidToken as exc:
        raise RuntimeError("Failed to decrypt data (invalid encryption key or corrupted data).") from exc


def encrypt_embedding(raw: bytes) -> bytes:
    """Encrypt embedding bytes for storage."""

    return encrypt_bytes(raw)


def decrypt_embedding(ciphertext: bytes) -> bytes:
    """Decrypt embedding bytes from storage."""

    return decrypt_bytes(ciphertext)


def encrypt_text(plain_text: str) -> bytes:
    """Encrypt arbitrary text for storage."""

    return encrypt_bytes(plain_text.encode("utf-8"))


def decrypt_text(ciphertext: bytes) -> str:
    """Decrypt arbitrary text from storage."""

    return decrypt_bytes(ciphertext).decode("utf-8")

