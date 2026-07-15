"""Stable identifiers shared by evidence validation and graph construction."""


def normalized_news_id(value: int | str | None) -> str | None:
    """Return a non-empty, trimmed article identifier or ``None`` when absent."""
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
