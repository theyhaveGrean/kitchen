"""Remove shopping annotations and non-ingredient notes from ingredient lines."""

from __future__ import annotations

import re

_PRICE = re.compile(r"(?:\s*[-–—]\s*)?\$\s*\d+(?:\.\d{2})?(?:\s*/\s*(?:oz|lb|kg|g|each))?", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\s*\([^()]*\)")
_CATALOG = re.compile(r"\s+(?:SKU|UPC|product code)\s*[:#]?\s*[\w-]+.*$", re.IGNORECASE)
_PREPARATION = re.compile(
    r"\b(?:chopped|diced|minced|sliced|shredded|grated|peeled|crushed|"
    r"drained|rinsed|melted|softened|room temperature|freshly cracked|"
    r"cut into|halved|quartered|divided)\b",
    re.IGNORECASE,
)


def _parenthetical(match: re.Match[str]) -> str:
    note = match.group().strip(" () ,")
    return f", {note}" if _PREPARATION.search(note) else ""


def clean_ingredient(ingredient: str) -> str:
    """Keep the amount and ingredient wording; remove prices and side notes."""
    cleaned = _PRICE.sub("", ingredient)
    cleaned = _PARENTHETICAL.sub(_parenthetical, cleaned)
    cleaned = _CATALOG.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;.-")
    return cleaned


def clean_all(ingredients: list[str]) -> list[str]:
    return [clean_ingredient(item) for item in ingredients if clean_ingredient(item)]
