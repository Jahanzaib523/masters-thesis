from functools import lru_cache
import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("sas.config")


class Settings(BaseSettings):
    """Application configuration settings.

    Values can be overridden via environment variables or a `.env` file.
    """

    model_config = SettingsConfigDict(
        env_file=("app/.env", ".env"),
        env_file_encoding="utf-8",
        # Empty HF_API_TOKEN="" in .env must not wipe a real token from the OS environment.
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "Semantic Authentication System (SAS)"
    app_version: str = "0.1.0"

    # Public browser origin for CORS (set in .env as FRONTEND_ORIGIN, e.g. https://yourdomain.com)
    frontend_origin: str = "http://localhost:5173"

    # Database
    database_url: str = "sqlite:///./sas.db"

    # Semantic / AI configuration
    # "hf"   -> HuggingFace / sentence-transformers local embeddings
    # "groq" -> Groq LLM-based semantic scoring
    embedding_provider: str = "hf"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    similarity_threshold: float = 0.7

    # Login / security behaviour
    max_login_attempts: int = 3
    semantic_lockout_start_after_failures: int = 3
    semantic_lockout_delays_seconds: str = "30,60,1800,3600"
    semantic_hard_lock_after_failures: int = 8

    # Groq Cloud configuration (all free tier)
    groq_api_key: str | None = None
    groq_model_id: str = "llama-3.1-8b-instant"  # Text LLM for semantic scoring
    groq_stt_model_id: str = "whisper-large-v3-turbo"  # Speech-to-text
    groq_tts_model_id: str = "canopylabs/orpheus-v1-english"  # Text-to-speech
    groq_tts_voice: str = "hannah"

    # OpenAI (optional) — chat completions for semantic summary + login similarity when client selects OpenAI
    openai_api_key: str | None = None
    # Override in .env: OPENAI_MODEL=gpt-4o or gpt-4o-mini, etc. (see OpenAI model docs)
    openai_model: str = "gpt-4o-mini"

    # Greeting image generation (anti-phishing visual cue)
    image_provider: str = "hf"
    # Default model served via Hugging Face Inference Providers (e.g. fal-ai, replicate).
    image_model: str = "black-forest-labs/FLUX.1-schnell"
    # Inference Providers routing: "auto" picks the first available provider for the model.
    # Override with e.g. "fal-ai", "replicate", "together", "nebius", "hf-inference".
    image_inference_provider: str = "auto"
    image_size: str = "1024x1024"
    image_style_preset: str = "minimal vector illustration, clean shapes, no text"
    fal_api_key: str | None = None
    hf_api_token: str | None = None
    hf_token: str | None = None

    # Crypto / auth tokens
    sas_encryption_key: str | None = None  # Fernet key (base64 urlsafe 32 bytes)
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60
    admin_unlock_secret: str | None = None

    @model_validator(mode="after")
    def _normalize_hf_tokens(self):
        """Allow either HF_API_TOKEN or HF_TOKEN from environment."""
        if self.hf_api_token is not None:
            self.hf_api_token = self.hf_api_token.strip() or None
        if self.hf_token is not None:
            self.hf_token = self.hf_token.strip() or None
        if not self.hf_api_token and self.hf_token:
            self.hf_api_token = self.hf_token
        return self


def resolve_hf_api_token() -> str | None:
    """Return HF token from loaded settings, then from process environment.

    Use this for Hugging Face API calls so `HF_API_TOKEN=""` in `.env` cannot hide a real OS token.
    """
    import os

    s = get_settings()
    t = (s.hf_api_token or "").strip()
    if t:
        return t
    for key in ("HF_API_TOKEN", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            logger.info(
                "resolve_hf_api_token: using env %s (len=%d, prefix=%s)",
                key,
                len(v),
                v[:4],
            )
            return v
    return None


def log_hf_env_diagnostics() -> None:
    """Log where HF tokens appear (never log secret values)."""
    import os

    keys = ("HF_API_TOKEN", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN")
    for key in keys:
        raw = os.environ.get(key)
        if raw is None:
            logger.info("HF diagnostic env[%s]=absent", key)
        elif not raw.strip():
            logger.warning(
                "HF diagnostic env[%s]=empty_string (ignored if env_ignore_empty applies)",
                key,
            )
        else:
            logger.info(
                "HF diagnostic env[%s]=present len=%s prefix=%s",
                key,
                len(raw),
                raw[:4],
            )
    s = get_settings()
    tok = (s.hf_api_token or "").strip()
    logger.info(
        "HF diagnostic settings.hf_api_token=%s",
        "present len=%d" % len(tok) if tok else "missing",
    )
    resolved = resolve_hf_api_token()
    logger.info(
        "HF diagnostic resolve_hf_api_token=%s",
        ("available len=%d" % len(resolved)) if resolved else "missing",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()


settings = get_settings()

