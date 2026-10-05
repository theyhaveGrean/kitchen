"""Compile validated semantics into graph plumbing without model calls."""

from __future__ import annotations

from .canonical import CanonicalRecipe
from .graph import GraphEdge, GraphNode, RecipeGraph
from .graph_measurements import parse_duration, parse_temperature
from .semantic import SemanticRecipe, SourceParameters
from .semantic_topology import get_terminal_operations
from .semantic_validation import has_errors, validate_semantic

GRAPH_COMPILER_VERSION = "semantic-compiler-v1"


def _node(node_id: str, kind: str, label: str, **fields: object) -> GraphNode:
    return GraphNode.model_validate(
        {
            "id": node_id,
            "type": kind,
            "label": label,
            "ingredient_id": None,
            "quantity": None,
            "unit": None,
            "preparation": None,
            "original_text": None,
            "step_index": None,
            "source_instruction": None,
            "action": None,
            "temperature": None,
            "duration": None,
            "heat_level": None,
            "equipment": [],
            "completion_condition": None,
            **fields,
        }
    )


def _operation(node_id: str, op: SourceParameters, canonical: CanonicalRecipe) -> GraphNode:
    return _node(
        node_id,
        "operation",
        op.action.capitalize(),
        action=op.action,
        step_index=op.step_index,
        source_instruction=canonical.instructions[op.step_index - 1].text,
        temperature=parse_temperature(op.temperature),
        duration=parse_duration(op.duration),
        heat_level=op.heat_level,
        equipment=op.equipment,
        completion_condition=op.completion_condition,
    )


def build_recipe_graph(canonical: CanonicalRecipe, semantic: SemanticRecipe) -> RecipeGraph:
    issues = validate_semantic(canonical, semantic)
    if has_errors(issues):
        raise ValueError(
            "Cannot compile invalid semantics: "
            + "; ".join(
                f"{issue.code}: {issue.message}" for issue in issues if issue.severity == "error"
            )
        )
    terminal = get_terminal_operations(semantic)[0]
    nodes = [
        _node(
            item.id,
            "ingredient",
            item.name or item.original_text,
            ingredient_id=item.id,
            quantity=item.quantity,
            unit=item.unit,
            preparation=item.preparation,
            original_text=item.original_text,
        )
        for item in canonical.ingredients
    ]
    edges: list[GraphEdge] = []
    for op in semantic.operations:
        nodes.append(_operation(op.id, op, canonical))
        for ref in op.inputs:
            source = f"{ref}_out" if ref.startswith("op_") else ref
            edges.append(GraphEdge(source=source, target=op.id, type="input"))
        output_id = "final_dish" if op.id == terminal else f"{op.id}_out"
        nodes.append(
            _node(
                output_id,
                "final" if op.id == terminal else "intermediate",
                canonical.title if op.id == terminal else op.output_name or "prepared mixture",
            )
        )
        edges.append(GraphEdge(source=op.id, target=output_id, type="output"))
    for index, prep in enumerate(semantic.prep_actions, 1):
        prep_id = f"prep_{index:03d}"
        nodes.append(_operation(prep_id, prep, canonical))
        # Source-ordered header actions are displayed independently. No guessed dependency edges.
    return RecipeGraph(
        nodes=nodes,
        edges=edges,
        unresolved_references=semantic.unresolved_references,
        warnings=[
            f"{issue.code}: {issue.message}" for issue in issues if issue.severity == "warning"
        ],
    )
