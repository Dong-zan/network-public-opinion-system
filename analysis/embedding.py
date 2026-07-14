"""Sentence-transformer embedding generation for one news item."""

from __future__ import annotations

from typing import Any

from .dependencies import get_sentence_transformer_class


MODEL_NAME = "shibing624/text2vec-base-chinese"
EMBEDDING_SIZE = 768

_MODEL: Any = None


def _get_model() -> Any:
    global _MODEL
    if _MODEL is None:
        _MODEL = get_sentence_transformer_class()(MODEL_NAME)
    return _MODEL


def generate_embedding(text: str) -> list[float]:
    """Return a normalized 768-dimensional semantic embedding."""
    vector = _get_model().encode(
        str(text or ""),
        normalize_embeddings=True,
    )
    values = vector.tolist() if hasattr(vector, "tolist") else list(vector)
    embedding = [float(value) for value in values]

    if len(embedding) != EMBEDDING_SIZE:
        raise ValueError(
            f"embedding dimension mismatch: expected {EMBEDDING_SIZE}, got {len(embedding)}"
        )

    return embedding
