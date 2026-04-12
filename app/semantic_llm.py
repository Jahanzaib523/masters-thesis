"""Dispatch semantic summary + similarity to Groq or OpenAI based on client preference."""

from __future__ import annotations

from typing import Optional

from .llm_provider import SemanticLlmBackend
from . import groq_client, openai_client


def generate_semantic_summary(text: str, backend: SemanticLlmBackend) -> Optional[str]:
    if backend == SemanticLlmBackend.openai:
        return openai_client.generate_semantic_summary(text)
    return groq_client.generate_semantic_summary(text)


def score_semantic_similarity(secret_text: str, attempt_text: str, backend: SemanticLlmBackend) -> Optional[float]:
    if backend == SemanticLlmBackend.openai:
        return openai_client.score_semantic_similarity(secret_text, attempt_text)
    return groq_client.score_semantic_similarity(secret_text, attempt_text)
