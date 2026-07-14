"""Utilities for maintaining normalized 768-dimensional embedding centers."""

from __future__ import annotations

from math import sqrt
from typing import List


EMBEDDING_DIMENSION = 768


def normalize_embedding(embedding: List[float]) -> List[float]:
    """Return an L2-normalized copy of a 768-dimensional embedding."""
    values = _validated_embedding(embedding)
    norm = sqrt(sum(value * value for value in values))

    if norm == 0:
        return [0.0] * EMBEDDING_DIMENSION

    return [value / norm for value in values]


def merge_embedding_center(
    old_embedding: List[float],
    old_count: int,
    new_embedding: List[float],
) -> List[float]:
    """Incrementally merge one embedding into an existing event center."""
    if old_count < 1:
        raise ValueError("old_count must be at least 1")

    old_values = _validated_embedding(old_embedding)
    new_values = _validated_embedding(new_embedding)
    new_count = old_count + 1
    merged = [
        (old_value * old_count + new_value) / new_count
        for old_value, new_value in zip(old_values, new_values)
    ]
    return normalize_embedding(merged)


def _validated_embedding(embedding: List[float]) -> List[float]:
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"embedding must contain exactly {EMBEDDING_DIMENSION} values"
        )

    try:
        return [float(value) for value in embedding]
    except (TypeError, ValueError) as exc:
        raise ValueError("embedding values must be numeric") from exc
