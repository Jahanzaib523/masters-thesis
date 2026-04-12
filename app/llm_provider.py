"""Which backend handles chat-based semantic summary + similarity scoring."""

from enum import Enum
from typing import Annotated, Optional

from fastapi import Header, HTTPException, status

from .config import settings


class SemanticLlmBackend(str, Enum):
    groq = "groq"
    openai = "openai"


def get_semantic_llm_backend(
    x_semantic_llm_provider: Annotated[
        Optional[str],
        Header(alias="X-Semantic-LLM-Provider", description="Use `openai` for OpenAI chat; omit or `groq` for Groq."),
    ] = None,
) -> SemanticLlmBackend:
    """Resolve LLM backend from client header. Defaults to Groq."""

    raw = (x_semantic_llm_provider or "").strip().lower()
    if raw in ("openai", "open_ai"):
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OpenAI semantic LLM was requested but OPENAI_API_KEY is not configured on the server.",
            )
        return SemanticLlmBackend.openai
    return SemanticLlmBackend.groq
