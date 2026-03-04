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
from typing import Optional

from groq import Groq

from .config import settings

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

    system_prompt = (
        "You are a semantic similarity scorer for an authentication system. "
        "The stored concept is a MULTI-ANGLE summary of a secret phrase. "
        "The login attempt may describe the same phrase from ANY valid angle: "
        "a paraphrase, a factual description, a cultural reference, a linguistic property, "
        "an analogy, a translation, or a descriptive interpretation. "
        "\n\n"
        "Scoring rules:\n"
        "1. Ask: 'Could this login attempt plausibly be describing the SAME phrase or concept as the stored summary?' "
        "   If yes from any angle → high score.\n"
        "2. Score 0.85-1.0: Attempt clearly identifies the same concept from any valid angle "
        "   (e.g. stored = pangram about a fox and dog; attempt = 'contains all English alphabet letters' → 0.9).\n"
        "3. Score 0.65-0.84: Attempt mostly identifies the concept but is somewhat incomplete or indirect.\n"
        "4. Score 0.35-0.64: Attempt shares some aspect but misses the core or is ambiguous.\n"
        "5. Score 0.0-0.34: Attempt is vague, generic, unrelated, or only mentions a trivial surface detail "
        "   that could apply to thousands of phrases (e.g. just 'I know' or just 'summer' or just 'dog').\n"
        "\n"
        "Give ONLY one number between 0 and 1, no explanation."
    )

    user_prompt = (
        "Stored concept (summary of user's secret):\n"
        f"{secret_text}\n\n"
        "Login attempt:\n"
        f"{attempt_text}\n\n"
        "Score (0-1):"
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        content = completion.choices[0].message.content.strip()
        first_token = content.split()[0]
        score = float(first_token)
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

    system_prompt = (
        "You are a semantic indexer for an authentication system. "
        "A user registers with a secret phrase. Your job is to generate a RICH, MULTI-ANGLE summary "
        "so that ANY valid description of the phrase can be matched at login time. "
        "\n\n"
        "Cover ALL of the following angles that apply:\n"
        "1. LITERAL MEANING: What does the phrase literally describe? (who, what, action, setting)\n"
        "2. CONCEPTUAL/FACTUAL: Is this phrase known for a specific property or fact? "
        "   (e.g. a pangram contains all alphabet letters; a palindrome reads same both ways; "
        "   a famous quote has an author; a riddle has an answer)\n"
        "3. CULTURAL/COMMON KNOWLEDGE: Is this phrase famous, a proverb, a movie title, a saying? "
        "   What is it commonly associated with or known as?\n"
        "4. STRUCTURAL/LINGUISTIC: Any notable linguistic feature (all letters, rhyme, alliteration, "
        "   wordplay, translation, language it is in)?\n"
        "5. ABSTRACT THEME: What broader idea, emotion, or theme does it represent?\n"
        "\n"
        "Output a dense summary (3-6 sentences) covering as many of these angles as apply. "
        "Be specific enough that descriptive interpretations, paraphrases, factual descriptions, "
        "cultural references, and analogies would all match. "
        "Do NOT store the raw phrase—abstract it but keep all meaningful angles."
    )

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Secret phrase: {text}"},
            ],
            temperature=0.0,
            max_tokens=150,
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



