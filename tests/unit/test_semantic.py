"""Saved semantic fixtures protect source fidelity and nontrivial material topology."""

import json
from pathlib import Path

import pytest

from recipe_scraper.canonical import canonical_from_json
from recipe_scraper.graph_compile import build_recipe_graph
from recipe_scraper.graph_render import render_svg
from recipe_scraper.presentation import render_prose, render_table
from recipe_scraper.semantic import SemanticRecipe
from recipe_scraper.semantic_topology import (
    can_render_as_table,
    get_terminal_operations,
    is_acyclic,
)
from recipe_scraper.semantic_validation import has_errors, validate_semantic

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/semantic_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case"])
def test_saved_semantic_quality(case):
    canonical = canonical_from_json(case["recipe"])
    semantic = SemanticRecipe.model_validate(case["semantic"])
    issues = validate_semantic(canonical, semantic)
    assert not has_errors(issues), issues
    graph = build_recipe_graph(canonical, semantic)
    assert is_acyclic(semantic) and len(get_terminal_operations(semantic)) == 1
    assert len([node for node in graph.nodes if node.type == "ingredient"]) == len(
        canonical.ingredients
    )
    assert len([node for node in graph.nodes if node.type == "final"]) == 1
    for ingredient in canonical.ingredients:
        node = next(node for node in graph.nodes if node.id == ingredient.id)
        assert (node.label, node.quantity, node.unit, node.preparation, node.original_text) == (
            ingredient.name or ingredient.original_text,
            ingredient.quantity,
            ingredient.unit,
            ingredient.preparation,
            ingredient.original_text,
        )
    for operation in semantic.operations:
        node = next(node for node in graph.nodes if node.id == operation.id)
        assert node.label == operation.action.capitalize()
        assert node.source_instruction == canonical.instructions[operation.step_index - 1].text
    assert render_prose(canonical, semantic) == [step.text for step in canonical.instructions]
    svg = render_svg(graph)
    assert "<svg" in svg
    for operation in semantic.operations:
        assert all(equipment not in svg for equipment in operation.equipment)
    table = render_table(canonical, semantic)
    if can_render_as_table(semantic):
        assert table and "<table>" in table
    else:
        assert table is None


@pytest.mark.parametrize(
    "change, code",
    [
        ("unknown_ingredient", "UNKNOWN_INGREDIENT"),
        ("unknown_operation", "UNKNOWN_OPERATION"),
        ("forward", "FORWARD_REFERENCE"),
        ("cycle", "CYCLE"),
        ("empty", "EMPTY_INPUTS"),
        ("duplicate_id", "DUPLICATE_OPERATION_ID"),
        ("step", "INVALID_STEP_INDEX"),
        ("duration", "INVENTED_DURATION"),
        ("temperature", "INVENTED_TEMPERATURE"),
        ("equipment", "INVENTED_EQUIPMENT"),
        ("unused", "UNUSED_INGREDIENT"),
        ("terminals", "MULTIPLE_TERMINALS"),
        ("duplicate_operation", "SUSPICIOUS_DUPLICATE_OPERATION"),
        ("verbose", "ACTION_TOO_VERBOSE"),
        ("portion", "INVENTED_PORTION"),
        ("metadata_output", "INVALID_OUTPUT_NAME"),
    ],
)
def test_semantic_validation_issues_are_structured(change, code):
    canonical = canonical_from_json(CASES[0]["recipe"])
    semantic = SemanticRecipe.model_validate(CASES[0]["semantic"])
    first, last = semantic.operations
    if change == "unknown_ingredient":
        first.inputs[0] = "ing_999"
    elif change == "unknown_operation":
        first.inputs[0] = "op_999"
    elif change in {"forward", "cycle"}:
        first.inputs.append(last.id)
    elif change == "empty":
        first.inputs = []
    elif change == "duplicate_id":
        last.id = first.id
    elif change == "step":
        first.step_index = 99
    elif change == "duration":
        first.duration = "10 minutes"
    elif change == "temperature":
        first.temperature = "375 F"
    elif change == "equipment":
        first.equipment = ["pressure cooker"]
    elif change == "unused":
        first.inputs.pop()
    elif change == "terminals":
        last.inputs = ["ing_001"]
    elif change == "duplicate_operation":
        semantic.operations.append(first.model_copy(update={"id": "op_003"}))
    elif change == "verbose":
        first.action = "mix the ingredients together until smooth"
    elif change == "metadata_output":
        first.output_name = "10 minutes"
    else:
        from recipe_scraper.semantic import Portion

        first.portions = [Portion(ref="ing_001", text="half")]
    issues = validate_semantic(canonical, semantic)
    assert any(issue.code == code and issue.severity == "error" for issue in issues)
    with pytest.raises(ValueError, match="Cannot compile"):
        build_recipe_graph(canonical, semantic)


def test_branching_and_reserved_materials_are_not_flattened():
    case = next(case for case in CASES if case["case"] == "cake_branches")
    semantic = SemanticRecipe.model_validate(case["semantic"])
    assert semantic.operations[2].inputs == ["op_001", "op_002"]
    assert can_render_as_table(semantic)
    reserved = next(case for case in CASES if case["case"] == "reserved_liquid")
    semantic = SemanticRecipe.model_validate(reserved["semantic"])
    assert not can_render_as_table(semantic)
