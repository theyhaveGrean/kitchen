import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from recipe_scraper.graph import (
    GraphEdge,
    GraphNode,
    GraphValidationError,
    RecipeGraph,
    validate_graph,
)
from recipe_scraper.graph_pipeline import cache_key, graph_input, load_cached_graph
from recipe_scraper.graph_render import graph_debug_text, render_svg


def node(node_id: str, node_type: str, label: str, **fields: object) -> GraphNode:
    data: dict[str, object] = {
        "id": node_id, "type": node_type, "label": label,
        "ingredient_id": None, "quantity": None, "unit": None, "preparation": None,
        "original_text": None, "step_index": None, "source_instruction": None,
        "temperature": None, "duration": None, "heat_level": None,
    }
    data.update(fields)
    return GraphNode.model_validate(data)


RECIPE = {
    "title": "Chopped Onion",
    "link": "https://example.test/onion",
    "ingredients": [{"quantity": "1", "unit": None, "ingredient": "onion", "preparation_type": None}],
    "recipe": ["Chop the onion.", "Serve the chopped onion."],
}


def sample_graph() -> RecipeGraph:
    return RecipeGraph(
        nodes=[
            node("ingredient_1", "ingredient", "onion", ingredient_id="ingredient_1", quantity="1", original_text="1 onion"),
            node("op_chop", "operation", "Chop", step_index=1, source_instruction="Chop the onion."),
            node("intermediate_onion", "intermediate", "Chopped onion"),
            node("op_serve", "operation", "Serve", step_index=2, source_instruction="Serve the chopped onion."),
            node("final_onion", "final", "Chopped Onion"),
        ],
        edges=[
            GraphEdge(source="ingredient_1", target="op_chop", type="input"),
            GraphEdge(source="op_chop", target="intermediate_onion", type="output"),
            GraphEdge(source="intermediate_onion", target="op_serve", type="input"),
            GraphEdge(source="op_serve", target="final_onion", type="output"),
        ],
        unresolved_references=[], warnings=[],
    )


def test_valid_graph_renders_and_uses_stable_input() -> None:
    graph = sample_graph()
    assert validate_graph(graph, RECIPE, ["1 onion"]) == []
    assert "Chopped onion" in graph_debug_text(graph)
    assert "<svg" in render_svg(graph)
    assert "Chopped" in render_svg(graph) and "Onion" in render_svg(graph)
    assert graph_input(RECIPE, ["1 onion"])["ingredients"][0]["id"] == "ingredient_1"
    assert cache_key(graph_input(RECIPE, ["1 onion"])) != cache_key(graph_input(RECIPE, ["one onion"]))


def test_cached_graph_is_read_without_regeneration(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    graph = sample_graph()
    path.write_text(json.dumps({
        "cache_key": cache_key(graph_input(RECIPE, ["1 onion"])),
        "graph": graph.model_dump(mode="json"),
    }), encoding="utf-8")
    assert load_cached_graph(path, RECIPE, ["1 onion"]) == (graph, [])
    assert load_cached_graph(path, RECIPE, ["another onion"]) is None


def test_original_lines_must_align() -> None:
    with pytest.raises(ValueError, match="align"):
        graph_input(RECIPE, [])


@pytest.mark.parametrize("change", ["duplicate", "missing_edge_node", "cycle", "unknown_ingredient", "missing_producer", "altered_instruction"])
def test_validator_rejects_malformed_graphs(change: str) -> None:
    graph = sample_graph()
    if change == "duplicate":
        graph.nodes.append(graph.nodes[0].model_copy())
    elif change == "missing_edge_node":
        graph.edges[0].source = "absent"
    elif change == "cycle":
        graph.edges.append(GraphEdge(source="op_serve", target="op_chop", type="dependency"))
    elif change == "unknown_ingredient":
        graph.nodes[0].ingredient_id = "ingredient_99"
    elif change == "altered_instruction":
        graph.nodes[1].source_instruction = "Chop two onions."
    else:
        graph.edges.pop()
    with pytest.raises(GraphValidationError):
        validate_graph(graph, RECIPE, ["1 onion"])


def test_validator_reports_uncertainty_without_inventing_edges() -> None:
    graph = sample_graph()
    graph.unresolved_references = ["which sauce is reserved"]
    graph.nodes.append(node("op_unused", "operation", "Preheat", step_index=1, source_instruction="Chop the onion."))
    warnings = validate_graph(graph, RECIPE, ["1 onion"])
    assert any("Unresolved reference" in warning for warning in warnings)
    assert any("Disconnected" in warning for warning in warnings)


def test_schema_rejects_unknown_node_type() -> None:
    with pytest.raises(ValidationError):
        node("thing", "unrecognized", "Thing")
