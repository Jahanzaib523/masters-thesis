from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import String, Integer, DateTime, ForeignKey, LargeBinary, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    """User account storing identifier and optional password hash."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    greeting_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    greeting_image_bytes: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    greeting_image_mime: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    greeting_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    greeting_prompt_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    greeting_model_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Login mode policy:
    # - "both": image pick + semantic step (default)
    # - "image_only": image pick only
    login_mode: Mapped[str] = mapped_column(String(32), default="both", nullable=False)
    semantic_failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    semantic_lock_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    semantic_locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    semantic_hard_locked: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    secret_embeddings: Mapped[list["SecretEmbedding"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    login_challenges: Mapped[list["LoginChallenge"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    login_events: Mapped[list["LoginEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class SecretType:
    TEXT = "text"
    VOICE = "voice"


class LoginMode:
    BOTH = "both"
    IMAGE_ONLY = "image_only"


class SecretEmbedding(Base):
    """Encrypted semantic data derived from the user's secret (text or voice)."""

    __tablename__ = "secret_embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Type of secret: "text" or "voice"
    secret_type: Mapped[str] = mapped_column(String(32), default=SecretType.TEXT, nullable=False)

    # Encrypted binary representation of the embedding vector (for local similarity)
    embedding_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    # Encrypted LLM-generated semantic summary (NOT raw text - for security)
    semantic_summary_encrypted: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    model_name: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="secret_embeddings")


class LoginChallengeStatus:
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"


class LoginChallenge(Base):
    """Represents a login attempt context for semantic authentication."""

    __tablename__ = "login_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(32), default=LoginChallengeStatus.PENDING, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow() + timedelta(minutes=10), nullable=False
    )
    # After password verification: user must pick the correct image from a 6-tile gallery before semantic step.
    image_gallery_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    image_pick_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    user: Mapped[User] = relationship(back_populates="login_challenges")
    gallery_slots: Mapped[list["LoginChallengeGallerySlot"]] = relationship(
        back_populates="challenge", cascade="all, delete-orphan"
    )


class LoginChallengeGallerySlot(Base):
    """Six images for a login challenge: one is the user's security image, five are decoys."""

    __tablename__ = "login_challenge_gallery_slots"
    __table_args__ = (UniqueConstraint("challenge_id", "slot", name="uq_gallery_challenge_slot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("login_challenges.id"), nullable=False, index=True)
    slot: Mapped[int] = mapped_column(Integer, nullable=False)  # 0..5
    image_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    image_mime: Mapped[str] = mapped_column(String(64), nullable=False)
    is_target: Mapped[bool] = mapped_column(default=False, nullable=False)

    challenge: Mapped["LoginChallenge"] = relationship(back_populates="gallery_slots")


class LoginResultType:
    SUCCESS = "success"
    FAILURE = "failure"
    LOCKED = "locked"


class LoginEvent(Base):
    """Audit log entry for an authentication attempt."""

    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)

    result: Mapped[str] = mapped_column(String(32), nullable=False)
    similarity_bucket: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped[Optional[User]] = relationship(back_populates="login_events")

