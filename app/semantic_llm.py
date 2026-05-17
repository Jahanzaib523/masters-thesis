"""Routes semantic requests to either Groq or OpenAI depending on what the client asked for."""

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


def generate_text_with_prompt(
    system_prompt: str,
    user_prompt: str,
    backend: SemanticLlmBackend,
    *,
    temperature: float = 0.0,
    max_tokens: int = 300,
) -> Optional[str]:
    """Send a prompt to the requested LLM backend and get text back."""
    if backend == SemanticLlmBackend.openai:
        return openai_client.generate_text_with_prompt(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return groq_client.generate_text_with_prompt(
        system_prompt,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
