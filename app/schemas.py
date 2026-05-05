from datetime import datetime
import re
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# Registration / profile secret text (login responses are not capped)
SECRET_TEXT_MAX_LENGTH = 100
PASSWORD_MIN_LENGTH = 8
STRICT_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PASSWORD_UPPER_RE = re.compile(r"[A-Z]")
PASSWORD_LOWER_RE = re.compile(r"[a-z]")
PASSWORD_DIGIT_RE = re.compile(r"\d")
PASSWORD_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


# ---- Core user models ----


class UserBase(BaseModel):
    username: str = Field(..., max_length=255)
    email: Optional[EmailStr] = None


class UserCreate(UserBase):
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        description="Required password used with your semantic secret when you sign in.",
    )
    secret_text: str = Field(
        ...,
        min_length=1,
        max_length=SECRET_TEXT_MAX_LENGTH,
        description=f"Meaningful secret phrase used to derive semantic embeddings (max {SECRET_TEXT_MAX_LENGTH} characters).",
    )
    image_text: str = Field(
        ...,
        min_length=1,
        max_length=SECRET_TEXT_MAX_LENGTH,
        description=f"Text used only to generate your greeting image (max {SECRET_TEXT_MAX_LENGTH} characters).",
    )
    secret_type: Literal["text", "voice"] = Field(
        default="text",
        description="Type of secret: text or voice (transcribed).",
    )

    @field_validator("email")
    @classmethod
    def validate_email_strict(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if not v:
            return None
        if not STRICT_EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, value: str) -> str:
        v = (value or "").strip()
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        if not PASSWORD_UPPER_RE.search(v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not PASSWORD_LOWER_RE.search(v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not PASSWORD_DIGIT_RE.search(v):
            raise ValueError("Password must contain at least one number.")
        if not PASSWORD_SPECIAL_RE.search(v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @field_validator("secret_text", "image_text")
    @classmethod
    def validate_non_empty_trimmed(cls, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("This field cannot be empty.")
        return v


class UserPublic(UserBase):
    id: int
    created_at: datetime
    secret_type: str = "text"

    class Config:
        from_attributes = True


# ---- Profile (authenticated) ----


class ProfileResponse(BaseModel):
    """Current user profile; includes secret_type (text or voice)."""

    id: int
    username: str
    email: Optional[str] = None
    created_at: datetime
    secret_type: str = Field(
        default="text",
        description="Current secret type: text or voice (one per account).",
    )
    login_mode: Literal["both", "image_only"] = Field(
        default="both",
        description="Current login mode: both factors or image-only.",
    )

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    """Optional fields to update on profile; only provided fields are updated. Send null or '' for email to clear it."""

    username: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    new_password: Optional[str] = Field(default=None, min_length=1)

    @field_validator("email")
    @classmethod
    def validate_profile_email_strict(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if not v:
            return ""
        if not STRICT_EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("new_password")
    @classmethod
    def validate_profile_password_policy(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if not v:
            return None
        if len(v) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        if not PASSWORD_UPPER_RE.search(v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not PASSWORD_LOWER_RE.search(v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not PASSWORD_DIGIT_RE.search(v):
            raise ValueError("Password must contain at least one number.")
        if not PASSWORD_SPECIAL_RE.search(v):
            raise ValueError("Password must contain at least one special character.")
        return v


class SecretUpdateText(BaseModel):
    """Update semantic secret to a new text phrase (overwrites voice if present)."""

    secret_text: str = Field(..., min_length=1, max_length=SECRET_TEXT_MAX_LENGTH)

    @field_validator("secret_text")
    @classmethod
    def validate_secret_trimmed(cls, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("secret_text cannot be empty.")
        return v


class GreetingImageUpdate(BaseModel):
    """Regenerate security greeting image from new image text only (semantic secret unchanged)."""

    image_text: str = Field(..., min_length=1, max_length=SECRET_TEXT_MAX_LENGTH)

    @field_validator("image_text")
    @classmethod
    def validate_image_text_trimmed(cls, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("image_text cannot be empty.")
        return v


class LoginModeUpdate(BaseModel):
    login_mode: Literal["both", "image_only"]


class RegistrationPreviewRequest(BaseModel):
    image_text: str = Field(..., min_length=1, max_length=SECRET_TEXT_MAX_LENGTH)

    @field_validator("image_text")
    @classmethod
    def validate_preview_text_trimmed(cls, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise ValueError("image_text cannot be empty.")
        return v


# ---- Auth / login schemas ----


class LoginInitRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Username or email used to identify the user.",
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Account password (required before the semantic prompt step).",
    )
    mode: Literal["text", "voice"] = Field(
        default="text",
        description="Login mode: text (type response) or voice (speak response).",
    )


class LoginInitResponse(BaseModel):
    challenge_id: int
    prompt: str = Field(
        ...,
        description="Human-readable instructions on how to answer using the secret idea.",
    )
    secret_type: str = Field(
        default="text",
        description="The type of secret registered (text or voice).",
    )
    audio_prompt_available: bool = Field(
        default=False,
        description="If true, TTS audio of the prompt is available at /auth/voice/prompt/{challenge_id}",
    )
    greeting_image_url: Optional[str] = Field(
        default=None,
        description="Deprecated: use greeting_gallery_urls (six-tile pick).",
    )
    greeting_gallery_urls: list[str] = Field(
        default_factory=list,
        description="Six images in slot order 0..5; exactly one matches the user's security image.",
    )
    semantic_required: bool = Field(
        default=True,
        description="If false, a correct image pick is enough to complete login (image_only mode).",
    )


class GreetingImagePickRequest(BaseModel):
    selected_slot: int = Field(..., ge=0, le=5, description="Which tile (0-5) is your security image.")


class GreetingImagePickResult(BaseModel):
    success: bool
    message: str
    token: Optional[str] = None
    remaining_attempts: Optional[int] = Field(
        default=None,
        description="After a wrong pick, how many tries remain before account lock.",
    )


class LoginCompleteRequest(BaseModel):
    challenge_id: int
    response_text: str = Field(
        ...,
        min_length=1,
        description="User's login response (any length; evaluated by semantic similarity).",
    )


class LoginResult(BaseModel):
    success: bool
    message: str
    similarity_score: Optional[float] = Field(
        default=None,
        description="Similarity score (only shown in debug/research mode).",
    )
    token: Optional[str] = None
    retry_after_seconds: Optional[int] = Field(
        default=None,
        description="If present, user must wait this many seconds before trying again.",
    )


class RecoveryRequest(BaseModel):
    identifier: str = Field(..., description="Username or email of the locked account.")


class RecoveryConfirmRequest(BaseModel):
    token: str = Field(..., min_length=1)


class RecoveryResponse(BaseModel):
    message: str
    recovery_token: Optional[str] = None


# ---- System / utility schemas ----


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str


class TTSResponse(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded WAV audio")
    text: str = Field(..., description="The text that was synthesized")

