"""Generate, validate, and cache semantic recipe graphs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .graph import GraphValidationError, RecipeGraph, validate_graph
from .llm import GRAPH_PROMPT, generate_recipe_graph, graph_model
from .structured_ingredients import ingredient_to_line


def source_ingredient_lines(recipe: dict[str, Any]) -> list[str]:
    return [
        item if isinstance(item, str) else ingredient_to_line(item)
        for item in recipe.get("ingredients", [])
    ]


def graph_input(recipe: dict[str, Any], original_ingredients: list[str] | None = None) -> dict[str, Any]:
    ingredients = recipe.get("ingredients")
    steps = recipe.get("recipe")
    if not isinstance(ingredients, list) or not all(isinstance(item, dict) for item in ingredients):
        raise ValueError("Graph input needs structured ingredients")
    if not isinstance(steps, list) or not all(isinstance(step, str) for step in steps):
        raise ValueError("Graph input needs instruction strings")
    if original_ingredients is not None and len(original_ingredients) != len(ingredients):
        raise ValueError("Original ingredient lines do not align with structured ingredients")
    return {
        "title": recipe.get("title"),
        "link": recipe.get("link"),
        "ingredients": [
            {
                "id": f"ingredient_{index}",
                "name": item.get("ingredient"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "preparation": item.get("preparation_type"),
                "original_text": original_ingredients[index - 1]
                if original_ingredients and index <= len(original_ingredients) else None,
            }
            for index, item in enumerate(ingredients, 1)
        ],
        "instructions": [{"index": index, "text": step} for index, step in enumerate(steps, 1)],
    }


def cache_key(recipe_input: dict[str, Any]) -> str:
    payload = {
        "input": recipe_input,
        "model": graph_model(),
        "prompt": GRAPH_PROMPT.read_text(encoding="utf-8"),
        "schema": RecipeGraph.model_json_schema(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def load_cached_graph(path: Path, recipe: dict[str, Any], original_ingredients: list[str] | None = None) -> tuple[RecipeGraph, list[str]] | None:
    if not path.exists():
        return None
    recipe_input = graph_input(recipe, original_ingredients)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("cache_key") != cache_key(recipe_input):
            return None
        graph = RecipeGraph.model_validate(data["graph"])
        return graph, validate_graph(graph, recipe, original_ingredients)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def get_or_generate_graph(path: Path, recipe: dict[str, Any], original_ingredients: list[str] | None = None) -> tuple[RecipeGraph, list[str], bool]:
    cached = load_cached_graph(path, recipe, original_ingredients)
    if cached is not None:
        return *cached, True
    recipe_input = graph_input(recipe, original_ingredients)
    graph = generate_recipe_graph(recipe_input)
    try:
        warnings = validate_graph(graph, recipe, original_ingredients)
    except GraphValidationError as exc:
        graph = generate_recipe_graph(recipe_input, graph, exc.errors)
        warnings = validate_graph(graph, recipe, original_ingredients)
    payload = {
        "cache_key": cache_key(recipe_input),
        "model": graph_model(),
        "graph": graph.model_dump(mode="json"),
        "validation_warnings": warnings,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return graph, warnings, False
