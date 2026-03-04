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
from functools import lru_cache
from typing import List, Sequence

from sentence_transformers import SentenceTransformer

from .config import settings

Vector = List[float]


class SemanticService:
    """Interface for semantic embedding and similarity operations."""

    def embed(self, text: str) -> Vector:
        """Convert input text into a numeric vector representation."""

        raise NotImplementedError

    def similarity(self, a: Sequence[float], b: Sequence[float]) -> float:
        """Return similarity score between two embedding vectors in [0, 1]."""

        raise NotImplementedError


class HFSentenceTransformerSemanticService(SemanticService):
    """Semantic service backed by a HuggingFace sentence-transformers model."""

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
    """Load and cache a sentence-transformers model."""

    return SentenceTransformer(model_name)


def vector_to_bytes(vector: Vector) -> bytes:
    """Serialize a numeric vector into bytes for storage."""

    return json.dumps(vector).encode("utf-8")


def bytes_to_vector(data: bytes) -> Vector:
    """Deserialize bytes back into a numeric vector."""

    loaded = json.loads(data.decode("utf-8"))
    return [float(x) for x in loaded]


# Default semantic service instance used by the application.
semantic_service: SemanticService = HFSentenceTransformerSemanticService(settings.embedding_model_name)

