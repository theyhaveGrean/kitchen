"""Compatibility facade: source recipe -> semantic cache -> compiled graph.

No direct graph-generation model path remains. Serialized graphs are derived artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .cache import content_hash, read_record, write_record
from .canonical import CanonicalRecipe, canonical_from_json
from .graph import RecipeGraph
from .graph_compile import GRAPH_COMPILER_VERSION, build_recipe_graph
from .llm import semantic_input
from .semantic_pipeline import get_semantic, load_semantic, semantic_cache_key, semantic_cache_path
from .structured_ingredients import ingredient_to_line


def source_ingredient_lines(recipe: dict[str, Any]) -> list[str]:
    if "instructions" in recipe:
        return [item["original_text"] for item in recipe["ingredients"]]
    return [
        item if isinstance(item, str) else ingredient_to_line(item)
        for item in recipe.get("ingredients", [])
    ]


def graph_input(
    recipe: dict[str, Any], original_ingredients: list[str] | None = None
) -> dict[str, Any]:
    return semantic_input(canonical_from_json(recipe, original_ingredients))


def cache_key(recipe_input: dict[str, Any]) -> str:
    canonical = CanonicalRecipe.model_validate(
        {
            "title": recipe_input["title"],
            "ingredients": [
                {"id": item["id"], "original_text": item["text"]}
                for item in recipe_input["ingredients"]
            ],
            "instructions": recipe_input["instructions"],
        }
    )
    return content_hash(
        {"semantic_key": semantic_cache_key(canonical), "compiler": GRAPH_COMPILER_VERSION}
    )


def _key(canonical: CanonicalRecipe) -> str:
    return content_hash(
        {
            "semantic_key": semantic_cache_key(canonical),
            "compiler": GRAPH_COMPILER_VERSION,
            "ingredient_display": [
                item.model_dump(exclude={"parsed"}) for item in canonical.ingredients
            ],
        }
    )


def load_cached_graph(
    path: Path, recipe: dict[str, Any], original_ingredients: list[str] | None = None
) -> tuple[RecipeGraph, list[str]] | None:
    canonical = canonical_from_json(recipe, original_ingredients)
    # Valid semantics are authoritative. Recompile on compiler-only changes without AI.
    inference = load_semantic(canonical, path.with_suffix(".semantic.json")) or load_semantic(
        canonical, semantic_cache_path(canonical)
    )
    if inference is None:
        return None
    graph = build_recipe_graph(canonical, inference.semantic)
    return graph, list(graph.warnings)


def get_or_generate_graph(
    path: Path, recipe: dict[str, Any], original_ingredients: list[str] | None = None
) -> tuple[RecipeGraph, list[str], bool]:
    canonical = canonical_from_json(recipe, original_ingredients)
    semantic_path = semantic_cache_path(canonical)
    inference = get_semantic(canonical, semantic_path)
    semantic_record = read_record(semantic_path, semantic_cache_key(canonical))
    if semantic_record is not None:
        write_record(path.with_suffix(".semantic.json"), semantic_record)
    graph = build_recipe_graph(canonical, inference.semantic)
    record = read_record(path, _key(canonical))
    if record is None:
        write_record(
            path,
            {
                "cache_key": _key(canonical),
                "compiler_version": GRAPH_COMPILER_VERSION,
                "graph": graph.model_dump(),
                "semantic_key": semantic_cache_key(canonical),
                "validation_warnings": graph.warnings,
                "provenance": inference.provenance,
            },
        )
    return graph, list(graph.warnings), inference.cached
