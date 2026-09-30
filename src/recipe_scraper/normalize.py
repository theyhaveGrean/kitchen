from __future__ import annotations

import html
import re
from collections.abc import Iterable
from typing import Any

from .models import Recipe
from .structured_ingredients import parse_ingredients


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _dedupe_key(value: str) -> str:
    value = clean_text(value).casefold()
    value = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", value)
    value = re.sub(r"[.!;,]+$", "", value).strip()
    return re.sub(r"\s+", " ", value)


def dedupe_recipe_lines(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean_text(value)
        key = _dedupe_key(text)
        if text and key and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def recipe_to_dict(recipe: Recipe, *, include_debug: bool = False) -> dict[str, Any]:
    """Serialize only the fields consumed by the product."""
    payload: dict[str, Any] = {
        "title": clean_text(recipe.title) or None,
        "link": recipe.source_url,
        "ingredients": parse_ingredients(dedupe_recipe_lines(recipe.ingredients)),
        "recipe": dedupe_recipe_lines(recipe.instructions),
    }
    if include_debug:
        payload["_debug"] = {
            "extraction_method": recipe.extraction_method,
            "confidence": recipe.confidence,
            "warnings": recipe.warnings,
        }
    return payload
