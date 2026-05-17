"""Bcrypt password hashing."""

from __future__ import annotations

import bcrypt

# bcrypt has a 72-byte maximum; we truncate to avoid errors
BCRYPT_MAX_PASSWORD_BYTES = 72


def _to_72_bytes(password: str) -> bytes:
    """Chop the password down to 72 bytes so bcrypt doesn't choke."""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        return encoded[:BCRYPT_MAX_PASSWORD_BYTES]
    return encoded


def hash_password(password: str | None) -> str | None:
    """Hash a password."""
    if not password:
        return None
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_to_72_bytes(password), salt)
    return hashed.decode("utf-8")


def verify_password(password: str | None, password_hash: str | None) -> bool:
    """Check if the password matches the hash."""
    if not password or not password_hash:
        return False
    return bcrypt.checkpw(_to_72_bytes(password), password_hash.encode("utf-8"))
