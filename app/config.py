from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration settings.

    Values can be overridden via environment variables or a `.env` file.
    """

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

    # Crypto / auth tokens
    sas_encryption_key: str | None = None  # Fernet key (base64 urlsafe 32 bytes)
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60

    class Config:
        # Support both project-root `.env` and `app/.env` (user may keep it under app/).
        env_file = ("app/.env", ".env")
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()


settings = get_settings()

