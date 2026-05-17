"""OpenAI client for semantic checks and summaries."""

Uses the same prompts as Groq. Configure model via OPENAI_MODEL (default: gpt-4o-mini).
See: https://platform.openai.com/docs/api-reference/chat/create
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from openai import OpenAI

from .config import settings
from .semantic_llm_prompts import (
    SIMILARITY_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    similarity_user_content,
    summary_user_content,
)

logger = logging.getLogger(__name__)


def get_openai_client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=settings.openai_api_key)


def score_semantic_similarity(secret_text: str, attempt_text: str) -> Optional[float]:
    """Use OpenAI to rate how similar two concepts are (0 to 1)."""

    try:
        client = get_openai_client()
    except RuntimeError as exc:
        logger.warning("OpenAI client not available: %s", exc)
        return None

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SIMILARITY_SYSTEM_PROMPT},
                {"role": "user", "content": similarity_user_content(secret_text, attempt_text)},
            ],
            temperature=0.0,
            max_tokens=250,
        )
        msg = completion.choices[0].message
        content = (msg.content or "").strip()
        logger.info("OpenAI scoring response: %s", content)
        match = re.search(r"SCORE:\s*([\d.]+)", content, re.IGNORECASE)
        if match:
            score = float(match.group(1))
        else:
            last_number = re.findall(r"[\d.]+", content)
            score = float(last_number[-1]) if last_number else 0.0
        return max(0.0, min(1.0, score))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to score similarity via OpenAI: %s", exc)
        return None


def generate_semantic_summary(text: str) -> Optional[str]:
    """Use OpenAI to summarize the secret text."""

    try:
        client = get_openai_client()
    except RuntimeError as exc:
        logger.warning("OpenAI client not available: %s", exc)
        return None

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": summary_user_content(text)},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        msg = completion.choices[0].message
        return (msg.content or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to generate semantic summary via OpenAI: %s", exc)
        return None


def generate_text_with_prompt(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 300,
) -> Optional[str]:
    """Generic helper to ping OpenAI for things like generating decoy prompts."""
    try:
        client = get_openai_client()
    except RuntimeError as exc:
        logger.warning("OpenAI client not available for generic prompt: %s", exc)
        return None

    try:
        completion = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        msg = completion.choices[0].message
        return (msg.content or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed generic OpenAI chat prompt: %s", exc)
        return None
