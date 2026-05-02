from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import JWTError, jwt

from .config import settings


def create_access_token(subject: str, extra_claims: Dict[str, Any] | None = None) -> str:
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")

    return create_signed_token(
        subject=subject,
        expires_minutes=settings.jwt_expires_minutes,
        extra_claims=extra_claims,
    )


def create_signed_token(
    subject: str,
    expires_minutes: int,
    extra_claims: Dict[str, Any] | None = None,
) -> str:
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")

    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=expires_minutes)

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Dict[str, Any] | None:
    """Decode and validate JWT; return payload or None if invalid/expired."""
    if not settings.jwt_secret_key:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError:
        return None

