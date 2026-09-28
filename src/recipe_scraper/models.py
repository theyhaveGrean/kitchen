from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Recipe:
    """Internal extraction model. The public JSON schema is intentionally smaller."""

    source_url: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    recipe_yield: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    cuisine: list[str] = field(default_factory=list)
    category: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    ingredient_sections: list[dict[str, Any]] = field(default_factory=list)
    instruction_sections: list[dict[str, Any]] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    nutrition: dict[str, Any] | None = None
    extraction_method: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
