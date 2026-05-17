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
    """Use Groq to rate how similar two concepts are."""

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
    """Use Groq to summarize the secret text."""

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


def generate_text_with_prompt(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 300,
) -> Optional[str]:
    """Generic helper to ping Groq for things like generating decoy prompts."""
    try:
        client = get_groq_client()
    except RuntimeError as exc:
        logger.warning("Groq client not available for generic prompt: %s", exc)
        return None

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return completion.choices[0].message.content.strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed generic Groq chat prompt: %s", exc)
        return None


# =============================================================================
# SPEECH-TO-TEXT (STT) - Groq Whisper
# =============================================================================


def transcribe_audio(filename: str, audio_bytes: bytes, language: str | None = None) -> Optional[str]:
    """Use Groq Whisper to turn audio into text."""

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
    """Use Groq Orpheus to turn text into speech."""

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



