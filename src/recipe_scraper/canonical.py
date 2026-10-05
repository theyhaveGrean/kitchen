"""Source-preserving, deterministic recipe boundary; ingredient parsing is advisory."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Recipe
from .normalize import clean_text, dedupe_recipe_lines
from .structured_ingredients import ingredient_to_line, parse_ingredient_line

CANONICAL_SCHEMA_VERSION = "1"


class CanonicalIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    original_text: str = Field(min_length=1)
    name: str | None = None
    quantity: str | None = None
    unit: str | None = None
    preparation: str | None = None
    parsed: dict[str, Any] | None = None


class CanonicalInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    text: str = Field(min_length=1)


class CanonicalRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    source_url: str | None = None
    canonical_url: str | None = None
    ingredients: list[CanonicalIngredient] = Field(min_length=1)
    instructions: list[CanonicalInstruction] = Field(min_length=1)
    yield_text: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_source_indices(self) -> Self:
        if [item.id for item in self.ingredients] != [
            f"ing_{i:03d}" for i in range(1, len(self.ingredients) + 1)
        ]:
            raise ValueError(
                "Canonical ingredient IDs must follow source order: ing_001, ing_002, ..."
            )
        if [step.index for step in self.instructions] != list(range(1, len(self.instructions) + 1)):
            raise ValueError("Canonical instruction indices must be consecutive and one-based")
        if (
            not self.title.strip()
            or any(not item.original_text.strip() for item in self.ingredients)
            or any(not step.text.strip() for step in self.instructions)
        ):
            raise ValueError("Canonical source content cannot be blank")
        return self

    def meaningful_content(self) -> dict[str, Any]:
        """Diagnostics and harmless URL tracking changes do not alter inference."""
        return {
            "title": self.title,
            "ingredients": [
                {"id": item.id, "original_text": item.original_text} for item in self.ingredients
            ],
            "instructions": [step.model_dump() for step in self.instructions],
        }

    def product_json(self, instructions: list[str] | None = None) -> dict[str, Any]:
        return {
            "title": self.title,
            "link": self.source_url or self.canonical_url,
            "ingredients": [
                {
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "ingredient": item.name or item.original_text,
                    "preparation_type": item.preparation,
                }
                for item in self.ingredients
            ],
            "recipe": instructions
            if instructions is not None
            else [step.text for step in self.instructions],
        }


def canonicalize(recipe: Recipe) -> CanonicalRecipe:
    lines = dedupe_recipe_lines(recipe.ingredients)
    items: list[CanonicalIngredient] = []
    warnings = list(recipe.warnings)
    parsed: dict[str, Any] | None
    for index, line in enumerate(lines, 1):
        try:
            parsed = dict(parse_ingredient_line(line))
        except Exception as exc:
            # Parser availability/uncertainty must never erase source text.
            parsed = None
            warnings.append(f"Ingredient {index} parsing unavailable: {type(exc).__name__}")
        items.append(
            CanonicalIngredient(
                id=f"ing_{index:03d}",
                original_text=line,
                name=parsed["ingredient"] if parsed else None,
                quantity=parsed["quantity"] if parsed else None,
                unit=parsed["unit"] if parsed else None,
                preparation=parsed["preparation_type"] if parsed else None,
                parsed=parsed,
            )
        )
    return CanonicalRecipe(
        title=clean_text(recipe.title),
        source_url=recipe.source_url,
        canonical_url=recipe.canonical_url,
        ingredients=items,
        instructions=[
            CanonicalInstruction(index=i, text=text)
            for i, text in enumerate(dedupe_recipe_lines(recipe.instructions), 1)
        ],
        yield_text=recipe.recipe_yield,
        prep_time=recipe.prep_time,
        cook_time=recipe.cook_time,
        total_time=recipe.total_time,
        metadata={
            **recipe.metadata,
            "extraction_method": recipe.metadata.get("extraction_method", recipe.extraction_method),
            "parser_method": recipe.extraction_method,
            "browser_fallback_used": recipe.browser_fallback_used,
            "warnings": warnings,
        },
    )


def canonical_from_json(
    data: dict[str, Any], original_ingredients: list[str] | None = None
) -> CanonicalRecipe:
    """Migrate saved product JSON; prefer an embedded canonical source when available."""
    if "instructions" in data:
        return CanonicalRecipe.model_validate(data)
    if isinstance(data.get("canonical"), dict):
        return CanonicalRecipe.model_validate(data["canonical"])
    ingredients = data.get("ingredients")
    steps = data.get("recipe")
    if (
        not isinstance(ingredients, list)
        or not isinstance(steps, list)
        or not all(isinstance(step, str) for step in steps)
    ):
        raise ValueError("Recipe requires ingredient and instruction arrays")
    if original_ingredients is not None and len(original_ingredients) != len(ingredients):
        raise ValueError("Original ingredient lines do not align with ingredients")
    items: list[CanonicalIngredient] = []
    for index, item in enumerate(ingredients, 1):
        if not isinstance(item, (str, dict)):
            raise ValueError("Recipe ingredients must be strings or objects")
        line = (
            original_ingredients[index - 1]
            if original_ingredients is not None
            else item
            if isinstance(item, str)
            else ingredient_to_line(item)
        )
        if isinstance(item, str):
            try:
                item = dict(parse_ingredient_line(item))
            except Exception:
                item = {"ingredient": None}
        items.append(
            CanonicalIngredient(
                id=f"ing_{index:03d}",
                original_text=line,
                name=item.get("ingredient"),
                quantity=item.get("quantity"),
                unit=item.get("unit"),
                preparation=item.get("preparation_type"),
            )
        )
    title = data.get("title")
    if not isinstance(title, str):
        raise ValueError("Recipe needs a title string")
    return CanonicalRecipe(
        title=title,
        source_url=data.get("link"),
        ingredients=items,
        instructions=[CanonicalInstruction(index=i, text=step) for i, step in enumerate(steps, 1)],
        metadata={
            "imported_product_json": True,
            "original_text_reconstructed": original_ingredients is None,
        },
    )
