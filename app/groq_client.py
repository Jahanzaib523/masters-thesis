"""
Groq Cloud client and helpers.

This module integrates with Groq's Python SDK to provide:
- Text LLM for semantic similarity scoring
- Speech-to-Text (STT) via Whisper
- Text-to-Speech (TTS) via Orpheus

All services use Groq's free tier.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from groq import Groq

from .config import settings
from .semantic_llm_prompts import (
    SIMILARITY_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    similarity_user_content,
    summary_user_content,
)

logger = logging.getLogger(__name__)


def get_groq_client() -> Groq:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")
    return Groq(api_key=settings.groq_api_key)


# =============================================================================
# TEXT LLM - Semantic Similarity Scoring
# =============================================================================


def score_semantic_similarity(secret_text: str, attempt_text: str) -> Optional[float]:
    """Use a Groq LLM to score semantic similarity between two texts.

    Returns a float in [0, 1] or None if scoring fails.
    """

    try:
        client = get_groq_client()
    except RuntimeError as exc:
        logger.warning("Groq client not available: %s", exc)
        return None

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model_id,
            messages=[
                {"role": "system", "content": SIMILARITY_SYSTEM_PROMPT},
                {"role": "user", "content": similarity_user_content(secret_text, attempt_text)},
            ],
            temperature=0.0,
            max_tokens=250,
        )
        content = completion.choices[0].message.content.strip()
        logger.info("LLM scoring response: %s", content)
        match = re.search(r"SCORE:\s*([\d.]+)", content, re.IGNORECASE)
        if match:
            score = float(match.group(1))
        else:
            last_number = re.findall(r"[\d.]+", content)
            score = float(last_number[-1]) if last_number else 0.0
        return max(0.0, min(1.0, score))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to score similarity via Groq: %s", exc)
        return None


def generate_semantic_summary(text: str) -> Optional[str]:
    """Use LLM to generate a semantic summary/concept of the secret.

    This summary is stored instead of raw text for security.
    It must capture the CORE idea so that paraphrases at login still match.
    """

    try:
        client = get_groq_client()
    except RuntimeError as exc:
        logger.warning("Groq client not available: %s", exc)
        return None

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model_id,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": summary_user_content(text)},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        return completion.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to generate semantic summary via Groq: %s", exc)
        return None


# =============================================================================
# SPEECH-TO-TEXT (STT) - Groq Whisper
# =============================================================================


def transcribe_audio(filename: str, audio_bytes: bytes, language: str | None = None) -> Optional[str]:
    """Transcribe audio bytes to text using Groq Whisper STT.

    Returns transcribed text or None if transcription fails.
    """

    try:
        client = get_groq_client()
    except RuntimeError as exc:
        logger.warning("Groq client not available: %s", exc)
        return None

    try:
        transcription = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=settings.groq_stt_model_id,
            response_format="json",
            temperature=0.0,
            language=language,
        )
        return getattr(transcription, "text", None) or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to transcribe audio via Groq: %s", exc)
        return None


# =============================================================================
# TEXT-TO-SPEECH (TTS) - Groq Orpheus
# =============================================================================


def synthesize_speech(text: str) -> Optional[bytes]:
    """Convert text to speech using Groq Orpheus TTS.

    Returns audio bytes (WAV format) or None if synthesis fails.
    """

    try:
        client = get_groq_client()
    except RuntimeError as exc:
        logger.warning("Groq client not available: %s", exc)
        return None

    try:
        response = client.audio.speech.create(
            model=settings.groq_tts_model_id,
            voice=settings.groq_tts_voice,
            input=text,
            response_format="wav",
        )
        # The response object has methods to get bytes
        return response.read()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to synthesize speech via Groq: %s", exc)
        return None



