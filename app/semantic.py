"""
Semantic service responsible for generating embeddings and computing similarity.

This is a lightweight, local placeholder implementation based on character
frequency vectors. It is intentionally simple and dependency-free so that it
can be swapped later for real embedding models (e.g. sentence-transformers,
Groq-hosted models) without changing the rest of the application.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import List, Sequence

from sentence_transformers import SentenceTransformer

from .config import resolve_hf_api_token, settings

Vector = List[float]


class SemanticService:
    """Base class for our embedding and similarity logic."""

    def embed(self, text: str) -> Vector:
        """Turn text into an array of numbers (an embedding)."""

        raise NotImplementedError

    def similarity(self, a: Sequence[float], b: Sequence[float]) -> float:
        """Compare two embeddings and return a score from 0 (different) to 1 (exact match)."""

        raise NotImplementedError


class HFSentenceTransformerSemanticService(SemanticService):
    """Our local Hugging Face sentence-transformers embedding setup."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = load_sentence_transformer(model_name)

    def embed(self, text: str) -> Vector:
        # sentence-transformers returns a numpy array; convert to list[float].
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def similarity(self, a: Sequence[float], b: Sequence[float]) -> float:
        # Cosine similarity between two vectors.
        if len(a) != len(b):
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return max(0.0, min(1.0, dot / (norm_a * norm_b)))


@lru_cache
def load_sentence_transformer(model_name: str) -> SentenceTransformer:
    """Spin up and cache the local sentence-transformers model so we don't load it twice."""
    # Keep HF Hub auth aligned with resolved token (settings + process env).
    tok = resolve_hf_api_token()
    if tok:
        os.environ.setdefault("HF_TOKEN", tok)
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", tok)
    return SentenceTransformer(model_name)


def vector_to_bytes(vector: Vector) -> bytes:
    """Convert an embedding vector into raw bytes so we can stick it in the database."""

    return json.dumps(vector).encode("utf-8")


def bytes_to_vector(data: bytes) -> Vector:
    """Convert database bytes back into an embedding vector."""

    loaded = json.loads(data.decode("utf-8"))
    return [float(x) for x in loaded]


# Default semantic service instance used by the application.
semantic_service: SemanticService = HFSentenceTransformerSemanticService(settings.embedding_model_name)

