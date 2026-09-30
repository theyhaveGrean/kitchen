"""Remove shopping annotations that Ingredient Parser may include in names."""

from __future__ import annotations

import re

_INLINE_PRICE = re.compile(
    r"\s*(?:[-–—]\s*)?\$\s*\d+(?:\.\d{2})?(?:\s*/\s*(?:oz|lb|kg|g|each))?\s*$",
    re.IGNORECASE,
)
_CATALOG = re.compile(r"\s+\(?(?:SKU|UPC|product code)\s*[:#]?\s*[\w-]+.*$", re.IGNORECASE)


def clean_ingredient(ingredient: str) -> str:
    """Remove shopping annotations before passing the line to Ingredient Parser."""
    cleaned = _INLINE_PRICE.sub("", ingredient)
    cleaned = _CATALOG.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;.-")
    return cleaned


def clean_all(ingredients: list[str]) -> list[str]:
    return [cleaned for item in ingredients if (cleaned := clean_ingredient(item))]
