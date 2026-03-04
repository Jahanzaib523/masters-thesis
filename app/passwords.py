"""Password hashing using bcrypt. Passwords are truncated to 72 bytes (bcrypt limit)."""

from __future__ import annotations

import bcrypt

# bcrypt has a 72-byte maximum; we truncate to avoid errors
BCRYPT_MAX_PASSWORD_BYTES = 72


def _to_72_bytes(password: str) -> bytes:
    """Return password as bytes, truncated to 72 bytes for bcrypt."""
    encoded = password.encode("utf-8")
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        return encoded[:BCRYPT_MAX_PASSWORD_BYTES]
    return encoded


def hash_password(password: str | None) -> str | None:
    """Hash a password with bcrypt. Returns None for empty/None password."""
    if not password:
        return None
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(_to_72_bytes(password), salt)
    return hashed.decode("utf-8")


def verify_password(password: str | None, password_hash: str | None) -> bool:
    """Verify a password against a bcrypt hash."""
    if not password or not password_hash:
        return False
    return bcrypt.checkpw(_to_72_bytes(password), password_hash.encode("utf-8"))
