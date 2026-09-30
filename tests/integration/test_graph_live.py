"""Real Luna semantic evaluation; set RUN_LIVE_GRAPH_TESTS=1 to make API calls."""

import json
import os
from pathlib import Path

import pytest

from recipe_scraper.graph import RecipeGraph
from recipe_scraper.graph_pipeline import get_or_generate_graph, load_cached_graph
from recipe_scraper.graph_render import render_svg

CASES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "graph_cases.json").read_text(encoding="utf-8"))


def reaches(graph: RecipeGraph, source_id: str, target_id: str) -> bool:
    adjacency: dict[str, set[str]] = {}
    for edge in graph.edges:
        adjacency.setdefault(edge.source, set()).add(edge.target)
    pending = [source_id]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target_id:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(adjacency.get(current, ()))
    return False


@pytest.mark.live
@pytest.mark.parametrize("case", CASES, ids=lambda item: item["case"])
def test_real_recipe_graph_semantics(case: dict[str, object], tmp_path: Path) -> None:
    if os.getenv("RUN_LIVE_GRAPH_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_GRAPH_TESTS=1 to call GPT-5.6 Luna")
    recipe = case["recipe"]
    assert isinstance(recipe, dict)
    cache_path = tmp_path / "graph.json"
    graph, warnings, cached = get_or_generate_graph(cache_path, recipe)
    assert not cached
    assert cache_path.exists()
    assert load_cached_graph(cache_path, recipe) == (graph, warnings)
    assert len([node for node in graph.nodes if node.type == "final"]) == 1
    assert any(node.type == "operation" for node in graph.nodes)
    assert "<svg" in render_svg(graph)
    final_id = next(node.id for node in graph.nodes if node.type == "final")
    if case["case"] != "ambiguous_reference":
        for index in range(1, len(recipe["ingredients"]) + 1):
            assert reaches(graph, f"ingredient_{index}", final_id)
    if case["case"] in {"pasta_separate_sauce", "cake_batter", "bread_dough", "marinade"}:
        assert any(node.type == "intermediate" for node in graph.nodes)
    if case["case"] in {"pasta_separate_sauce", "stir_fry_parallel"}:
        first_consumers = {
            ingredient_id: {edge.target for edge in graph.edges if edge.source == ingredient_id and edge.type == "input"}
            for ingredient_id in ("ingredient_1", "ingredient_2")
        }
        assert first_consumers["ingredient_1"]
        assert first_consumers["ingredient_2"]
        assert first_consumers["ingredient_1"].isdisjoint(first_consumers["ingredient_2"])
    if case["case"] == "divided_remaining":
        assert len({edge.target for edge in graph.edges if edge.source == "ingredient_2"}) >= 2
    if case["case"] == "ambiguous_reference":
        assert graph.unresolved_references
