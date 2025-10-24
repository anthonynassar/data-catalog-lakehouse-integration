"""Utility helpers for the semantic model generator."""

from __future__ import annotations

import html
import re
from typing import Iterable, List, Sequence

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str | None) -> str:
    """Return ``value`` with Collibra rich text markup removed.

    Collibra stores attribute values as HTML fragments.  Snowflake semantic
    model descriptions are plain text, so we strip tags and HTML entities.
    ``None`` inputs return an empty string to simplify callers.
    """

    if not value:
        return ""

    # Unescape HTML entities first (Collibra frequently escapes characters).
    text = html.unescape(value)
    # Remove tags and collapse whitespace.
    text = _HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_synonyms(values: Sequence[str]) -> List[str]:
    """Return a sorted list of unique synonyms.

    Collibra assets may contain duplicate synonyms across attributes and
    relations.  We deduplicate case-insensitively while preserving original
    casing of the first occurrence and return the results sorted for
    deterministic YAML output.
    """

    unique: dict[str, str] = {}
    for value in values:
        if not value:
            continue
        key = value.strip()
        if not key:
            continue
        lowered = key.lower()
        if lowered not in unique:
            unique[lowered] = key
    return sorted(unique.values())


def coalesce_first(*values: Iterable[str] | str | None) -> str:
    """Return the first non-empty string from ``values``.

    This helper simplifies "Definition" versus ``description`` fallbacks.
    """

    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, Iterable):
            for candidate in value:
                if candidate and candidate.strip():
                    return candidate
    return ""
