from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field

# Registration / profile secret text (login responses are not capped)
SECRET_TEXT_MAX_LENGTH = 100


# ---- Core user models ----


class UserBase(BaseModel):
    username: str = Field(..., max_length=255)
    email: Optional[EmailStr] = None


class UserCreate(UserBase):
    password: str = Field(
        ...,
        min_length=8,
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

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    """Optional fields to update on profile; only provided fields are updated. Send null or '' for email to clear it."""

    username: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    new_password: Optional[str] = Field(default=None, min_length=1)


class SecretUpdateText(BaseModel):
    """Update semantic secret to a new text phrase (overwrites voice if present)."""

    secret_text: str = Field(..., min_length=1, max_length=SECRET_TEXT_MAX_LENGTH)


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
        description="Server-rendered personal greeting image shown before semantic verification.",
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

