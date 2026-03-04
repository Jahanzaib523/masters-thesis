from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, EmailStr, Field


# ---- Core user models ----


class UserBase(BaseModel):
    username: str = Field(..., max_length=255)
    email: Optional[EmailStr] = None


class UserCreate(UserBase):
    password: Optional[str] = Field(
        default=None,
        description="Optional baseline password; semantic secret is still required.",
    )
    secret_text: str = Field(
        ...,
        min_length=10,
        description="Meaningful secret phrase used to derive semantic embeddings.",
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

    secret_text: str = Field(..., min_length=10)


# ---- Auth / login schemas ----


class LoginInitRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Username or email used to identify the user.",
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


class LoginCompleteRequest(BaseModel):
    challenge_id: int
    response_text: str = Field(
        ...,
        min_length=3,
        description="User's description/paraphrase/analogy of their secret idea.",
    )


class LoginResult(BaseModel):
    success: bool
    message: str
    similarity_score: Optional[float] = Field(
        default=None,
        description="Similarity score (only shown in debug/research mode).",
    )
    token: Optional[str] = None


# ---- System / utility schemas ----


class HealthResponse(BaseModel):
    status: str
    app_name: str
    version: str


class TTSResponse(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded WAV audio")
    text: str = Field(..., description="The text that was synthesized")

