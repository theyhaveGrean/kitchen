import json
from pathlib import Path
from xml.etree import ElementTree

import pytest
from pydantic import ValidationError

from recipe_scraper.graph import (
    Duration,
    GraphEdge,
    GraphNode,
    GraphValidationError,
    RecipeGraph,
    Temperature,
    validate_graph,
)
from recipe_scraper.graph_pipeline import (
    cache_key,
    graph_input,
    load_cached_graph,
)
from recipe_scraper.graph_render import graph_debug_text, render_svg


def node(node_id: str, node_type: str, label: str, **fields: object) -> GraphNode:
    data: dict[str, object] = {
        "id": node_id, "type": node_type, "label": label,
        "ingredient_id": None, "quantity": None, "unit": None, "preparation": None,
        "original_text": None, "step_index": None, "source_instruction": None,
        "temperature": {"min": None, "nominal": None, "max": None, "unit": None} if node_type == "operation" else None,
        "duration": {"min": None, "nominal": None, "max": None, "unit": None} if node_type == "operation" else None,
        "action": label.lower() if node_type == "operation" else None,
        "equipment": [], "completion_condition": None, "heat_level": None,
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
    assert graph_input(RECIPE, ["1 onion"])["ingredients"][0]["id"] == "ing_001"
    assert cache_key(graph_input(RECIPE, ["1 onion"])) != cache_key(graph_input(RECIPE, ["one onion"]))


def test_cached_graph_is_read_without_regeneration(tmp_path: Path) -> None:
    from recipe_scraper.canonical import canonical_from_json
    from recipe_scraper.graph_compile import build_recipe_graph
    from recipe_scraper.semantic import SemanticRecipe
    from recipe_scraper.semantic_pipeline import semantic_cache_key

    canonical = canonical_from_json(RECIPE, ["1 onion"])
    operations = []
    for index, action in enumerate(("chop", "serve"), 1):
        operations.append({"id": f"op_{index:03d}", "step_index": index, "action": action,
            "inputs": ["ing_001" if index == 1 else "op_001"], "output_name": None,
            "temperature": None, "duration": None, "heat_level": None,
            "equipment": [], "completion_condition": None, "portions": []})
    semantic = SemanticRecipe.model_validate({"operations": operations, "prep_actions": [], "unresolved_references": []})
    path = tmp_path / "graph.json"
    path.with_suffix(".semantic.json").write_text(json.dumps({
        "cache_key": semantic_cache_key(canonical), "semantic": semantic.model_dump(), "provenance": {},
    }), encoding="utf-8")
    assert load_cached_graph(path, RECIPE, ["1 onion"]) == (build_recipe_graph(canonical, semantic), [])
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


@pytest.mark.parametrize("fields", [
    {"action": None}, {"action": "oven"}, {"action": "golden brown"},
    {"label": "Chop onion"}, {"label": "Chop for 10 minutes"},
    {"duration": "10 minutes"}, {"temperature": "350 F"},
    {"duration": None}, {"temperature": None},
    {"equipment": [" "]}, {"equipment": ["oven", "Oven"]},
    {"completion_condition": ""},
])
def test_schema_rejects_unstructured_operation_metadata(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GraphNode.model_validate({**sample_graph().nodes[1].model_dump(), **fields})


@pytest.mark.parametrize("measurement, values", [
    (Duration, {"min": 15, "nominal": None, "max": 10, "unit": "minute"}),
    (Duration, {"min": 10, "nominal": 20, "max": 15, "unit": "minute"}),
    (Duration, {"min": -1, "nominal": None, "max": None, "unit": "minute"}),
    (Duration, {"min": True, "nominal": None, "max": None, "unit": "minute"}),
    (Duration, {"min": "10", "nominal": None, "max": None, "unit": "minute"}),
    (Duration, {"min": float("inf"), "nominal": None, "max": None, "unit": "minute"}),
    (Duration, {"min": 10, "nominal": None, "max": None, "unit": None}),
    (Temperature, {"min": 350, "nominal": None, "max": 375, "unit": "kelvin"}),
    (Temperature, {"min": 350, "nominal": None, "max": 375, "unit": None}),
])
def test_schema_rejects_invalid_measurements(measurement: type[Duration] | type[Temperature], values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        measurement.model_validate(values)


@pytest.mark.parametrize("fields", [
    {"action": "bake"}, {"equipment": ["oven"]}, {"completion_condition": "until tender"},
    {"duration": {"min": 10, "nominal": 10, "max": 10, "unit": "minute"}},
])
def test_only_operations_may_have_cooking_metadata(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        node("intermediate_onion", "intermediate", "Chopped onion", **fields)


def baking_graph(instruction: str) -> tuple[RecipeGraph, dict[str, object]]:
    graph = sample_graph()
    recipe: dict[str, object] = {**RECIPE, "recipe": [instruction, RECIPE["recipe"][1]]}
    operation = graph.nodes[1]
    operation.action = "bake"
    operation.label = "Bake"
    operation.source_instruction = instruction
    return graph, recipe


def test_structured_parameters_and_conditions_are_preserved_but_equipment_is_hidden() -> None:
    graph, recipe = baking_graph("Bake in a 9×9-inch baking pan at 350°F for 10–15 minutes until golden brown.")
    operation = graph.nodes[1]
    operation.duration = Duration(min=10, nominal=None, max=15, unit="minute")
    operation.temperature = Temperature(min=350, nominal=350, max=350, unit="F")
    operation.equipment = ["oven", "9×9-inch baking pan"]
    operation.completion_condition = "until golden brown"
    assert validate_graph(graph, recipe, ["1 onion"]) == []
    assert RecipeGraph.model_validate_json(graph.model_dump_json()) == graph
    svg = render_svg(graph)
    visible_text = " ".join(ElementTree.fromstring(svg).itertext())
    assert ">Bake<" in svg and "350°F" in visible_text and "10–15 min" in visible_text
    assert "baking pan" not in svg and "oven" not in svg
    assert "golden brown" not in svg


@pytest.mark.parametrize("field, value", [
    ("duration", Duration(min=10, nominal=10, max=10, unit="minute")),
    ("temperature", Temperature(min=350, nominal=350, max=350, unit="F")),
    ("equipment", ["stand mixer"]),
    ("completion_condition", "until golden brown"),
    ("action", None),
    ("duration", "10 minutes"),
    ("step_index", True),
])
def test_validator_rejects_invented_or_mutated_metadata(field: str, value: object) -> None:
    graph = sample_graph()
    setattr(graph.nodes[1], field, value)
    with pytest.raises(GraphValidationError):
        validate_graph(graph, RECIPE, ["1 onion"])


def test_range_nominal_cannot_be_invented() -> None:
    graph, recipe = baking_graph("Bake for 10 to 15 minutes.")
    graph.nodes[1].duration = Duration(min=10, nominal=12, max=15, unit="minute")
    with pytest.raises(GraphValidationError, match="Duration is unsupported"):
        validate_graph(graph, recipe, ["1 onion"])


def test_internal_temperature_is_a_completion_condition() -> None:
    graph, recipe = baking_graph("Bake until internal temperature reaches 165°F.")
    graph.nodes[1].completion_condition = "until internal temperature reaches 165°F"
    assert validate_graph(graph, recipe, ["1 onion"]) == []
    graph.nodes[1].temperature = Temperature(min=165, nominal=165, max=165, unit="F")
    with pytest.raises(GraphValidationError, match="Temperature is unsupported"):
        validate_graph(graph, recipe, ["1 onion"])


def test_old_schema_cache_is_not_reused(tmp_path: Path) -> None:
    graph = sample_graph().model_dump(mode="json")
    graph["nodes"][1]["duration"] = "10 minutes"
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"cache_key": cache_key(graph_input(RECIPE, ["1 onion"])), "graph": graph}))
    assert load_cached_graph(path, RECIPE, ["1 onion"]) is None


@pytest.mark.parametrize("label", ["oven", "prepared pan", "9×9-inch baking pan", "golden brown", "temperature"])
def test_metadata_and_equipment_are_not_material_products(label: str) -> None:
    with pytest.raises(ValidationError):
        node("intermediate_metadata", "intermediate", label)


@pytest.mark.parametrize("action", ["sauté", "torrefy", "stir fry", "set aside"])
def test_action_vocabulary_preserves_cooking_verbs(action: str) -> None:
    operation = node("op_action", "operation", action.capitalize())
    assert operation.action == action


@pytest.mark.parametrize("instruction, timing", [
    ("Bake for 10 minutes.", {"min": 10, "nominal": 10, "max": 10, "unit": "minute"}),
    ("Bake for 30 seconds.", {"min": 30, "nominal": 30, "max": 30, "unit": "second"}),
    ("Bake for at least 10 minutes.", {"min": 10, "nominal": None, "max": None, "unit": "minute"}),
    ("Bake for up to 15 minutes.", {"min": None, "nominal": None, "max": 15, "unit": "minute"}),
    ("Bake for 1 hour and 30 minutes.", {"min": 90, "nominal": 90, "max": 90, "unit": "minute"}),
    ("Bake for 1/2 hour.", {"min": 30, "nominal": 30, "max": 30, "unit": "minute"}),
    ("Bake for 10 more minutes.", {"min": 10, "nominal": 10, "max": 10, "unit": "minute"}),
    ("Bake for ten minutes.", {"min": 10, "nominal": 10, "max": 10, "unit": "minute"}),
    ("Bake for twenty-five minutes.", {"min": 25, "nominal": 25, "max": 25, "unit": "minute"}),
    ("Bake for half an hour.", {"min": 30, "nominal": 30, "max": 30, "unit": "minute"}),
])
def test_explicit_duration_forms_are_valid(instruction: str, timing: dict[str, object]) -> None:
    graph, recipe = baking_graph(instruction)
    graph.nodes[1].duration = Duration.model_validate(timing)
    assert validate_graph(graph, recipe, ["1 onion"]) == []


def test_temperature_ranges_and_deterministic_conversion() -> None:
    graph, recipe = baking_graph("Bake at 350–375°F.")
    graph.nodes[1].temperature = Temperature(min=350, nominal=None, max=375, unit="F")
    assert validate_graph(graph, recipe, ["1 onion"]) == []
    graph.nodes[1].temperature = Temperature(min=(350 - 32) * 5 / 9, nominal=None, max=(375 - 32) * 5 / 9, unit="C")
    assert validate_graph(graph, recipe, ["1 onion"]) == []


def test_unknown_parameters_do_not_show_placeholder_values() -> None:
    graph = sample_graph()
    svg = render_svg(graph)
    assert "null" not in svg and "0 min" not in svg and "°" not in svg
