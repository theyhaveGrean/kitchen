"""Recipe material-flow graph schema and deterministic validation."""

from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, StrictFloat, StrictInt, ValidationError, model_validator

NodeType = Literal["ingredient", "operation", "intermediate", "final"]
EdgeType = Literal["input", "output", "dependency"]
# Keep the action vocabulary open; validate its shape and reject metadata below.
CookingAction = str
_METADATA_ACTIONS = {
    "oven", "pan", "bowl", "container", "blender", "mixer", "equipment", "temperature",
    "duration", "time", "minute", "minutes", "hour", "hours", "second", "seconds",
    "smooth", "tender", "golden", "ready", "done", "cooked", "prepared", "hot", "cold",
}
_EQUIPMENT_LABEL = re.compile(
    r"^(?:(?:prepared|greased|heated|preheated|a|the)\s+)*"
    r"(?:\d+(?:[×x-]\d+)?[ -]inch\s+)?"
    r"(?:oven|broiler|(?:baking |mixing )?(?:pan|bowl)|Dutch oven|stand mixer|blender|"
    r"pressure cooker|air fryer|container|equipment|temperature|duration|time|"
    r"golden brown|tender|smooth)$", re.I,
)


def is_material_label(label: str) -> bool:
    text = label.strip()
    return (
        bool(text)
        and _EQUIPMENT_LABEL.fullmatch(text) is None
        and re.fullmatch(
            r"(?:until\s+)?(?:golden brown|tender|smooth|doubled in size|ready|done|hot|cold)",
            text, re.I,
        ) is None
        and re.fullmatch(
            r"\d+(?:\.\d+)?(?:\s*(?:[-–—]|to)\s*\d+(?:\.\d+)?)?\s*"
            r"(?:°?\s*[FC]|degrees?(?:\s*[FC])?|seconds?|minutes?|hours?|days?)",
            text, re.I,
        ) is None
    )


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: StrictFloat | None
    nominal: StrictFloat | None
    max: StrictFloat | None

    @model_validator(mode="after")
    def check_bounds(self) -> Self:
        values = [value for value in (self.min, self.nominal, self.max) if value is not None]
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Measurement values must be finite")
        if values != sorted(values):
            raise ValueError("Measurement requires min <= nominal <= max")
        return self


class Duration(Measurement):
    unit: Literal["second", "minute", "hour", "day"] | None

    @model_validator(mode="after")
    def check_duration(self) -> Self:
        values = [value for value in (self.min, self.nominal, self.max) if value is not None]
        if any(value < 0 for value in values):
            raise ValueError("Duration cannot be negative")
        if values and self.unit is None:
            raise ValueError("Duration values require a unit")
        return self


class Temperature(Measurement):
    unit: Literal["F", "C"] | None

    @model_validator(mode="after")
    def check_temperature(self) -> Self:
        if any(value is not None for value in (self.min, self.nominal, self.max)) and self.unit is None:
            raise ValueError("Temperature values require a unit")
        return self


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: NodeType
    label: str
    ingredient_id: str | None
    quantity: str | None
    unit: str | None
    preparation: str | None
    original_text: str | None
    step_index: StrictInt | None
    source_instruction: str | None
    action: CookingAction | None
    temperature: Temperature | None
    duration: Duration | None
    equipment: list[str]
    completion_condition: str | None
    heat_level: str | None

    @model_validator(mode="after")
    def check_operation_metadata(self) -> Self:
        if self.type in {"intermediate", "final"} and not is_material_label(self.label):
            raise ValueError("Product nodes must represent cooking material, not metadata or equipment")
        if self.type == "operation":
            if (self.action is None or self.action != self.action.casefold()
                    or not self.action.strip() or self.action.split()[0] in _METADATA_ACTIONS
                    or len(self.action.split()) > 4
                    or not all(word.isalpha() for word in self.action.replace("-", " ").split())):
                raise ValueError("Operation requires a meaningful cooking action")
            if self.label != self.action.capitalize():
                raise ValueError("Operation label must be the capitalized action alone")
            if self.duration is None or self.temperature is None:
                raise ValueError("Operations require structured duration and temperature objects")
            if any(not item.strip() or item != item.strip() for item in self.equipment):
                raise ValueError("Equipment entries must be non-empty and trimmed")
            if len({item.casefold() for item in self.equipment}) != len(self.equipment):
                raise ValueError("Duplicate equipment")
            if self.completion_condition is not None and not self.completion_condition.strip():
                raise ValueError("Completion condition must be non-empty or null")
        elif any(value is not None for value in (
            self.action, self.step_index, self.source_instruction, self.temperature,
            self.duration, self.heat_level, self.completion_condition,
        )) or self.equipment:
            raise ValueError("Only operations may have cooking metadata")
        if self.type != "ingredient" and any(value is not None for value in (
            self.ingredient_id, self.quantity, self.unit, self.preparation, self.original_text,
        )):
            raise ValueError("Only ingredients may have source ingredient metadata")
        return self


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    type: EdgeType


class RecipeGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    unresolved_references: list[str]
    warnings: list[str]


class GraphValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_graph(
    graph: RecipeGraph, recipe: dict[str, Any], original_ingredients: list[str] | None = None
) -> list[str]:
    """Reject structural mistakes; report uncertain or unused material as warnings."""
    from .graph_measurements import duration_supported, temperature_supported

    errors: list[str] = []
    warnings = list(graph.warnings)
    ingredients = recipe.get("ingredients")
    steps = recipe.get("recipe")
    if not isinstance(ingredients, list) or not isinstance(steps, list):
        raise GraphValidationError(["Recipe needs ingredient and instruction arrays"])

    ids = [node.id for node in graph.nodes]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate node IDs")
    if any(not node.id.strip() or not node.label.strip() for node in graph.nodes):
        errors.append("Blank node ID or label")
    nodes = {node.id: node for node in graph.nodes}
    adjacency: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, list[GraphEdge]] = defaultdict(list)
    outgoing: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in graph.edges:
        source, target = nodes.get(edge.source), nodes.get(edge.target)
        if source is None or target is None:
            errors.append(f"Edge references missing node: {edge.source} -> {edge.target}")
            continue
        valid_pair = (
            edge.type == "input" and source.type in {"ingredient", "intermediate"} and target.type == "operation"
            or edge.type == "output" and source.type == "operation" and target.type in {"intermediate", "final"}
            or edge.type == "dependency" and source.type == target.type == "operation"
        )
        if not valid_pair:
            errors.append(f"Invalid {edge.type} edge: {edge.source} -> {edge.target}")
        adjacency[edge.source].add(edge.target)
        incoming[edge.target].append(edge)
        outgoing[edge.source].append(edge)

    indegree = {node_id: 0 for node_id in nodes}
    for targets in adjacency.values():
        for target_id in targets:
            indegree[target_id] += 1
    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target_id in adjacency[current]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)
    if visited != len(nodes):
        errors.append("Graph contains a cycle")

    expected = {f"ingredient_{i}": item for i, item in enumerate(ingredients, 1)}
    seen_ingredients: set[str] = set()
    final_nodes = [node for node in graph.nodes if node.type == "final"]
    if len(final_nodes) != 1:
        errors.append("Graph must have exactly one final product")
    for node in graph.nodes:
        # Recheck models even when callers mutated an already parsed graph.
        try:
            GraphNode.model_validate(node.model_dump(warnings=False))
        except ValidationError as exc:
            errors.append(f"Invalid node metadata: {node.id}: {exc}")
            continue
        if node.type == "ingredient":
            ingredient = expected.get(node.ingredient_id or "")
            if ingredient is None or not isinstance(ingredient, dict):
                errors.append(f"Unknown source ingredient: {node.id}")
                continue
            if node.ingredient_id in seen_ingredients:
                errors.append(f"Duplicate source ingredient: {node.ingredient_id}")
            seen_ingredients.add(node.ingredient_id or "")
            if node.label.casefold().strip() != str(ingredient.get("ingredient", "")).casefold().strip():
                errors.append(f"Ingredient name differs from recipe: {node.id}")
            for field, key in (("quantity", "quantity"), ("unit", "unit"), ("preparation", "preparation_type")):
                if getattr(node, field) != ingredient.get(key):
                    errors.append(f"Ingredient {field} differs from recipe: {node.id}")
            ingredient_index = next(
                (index for index, ingredient_id in enumerate(expected) if ingredient_id == node.ingredient_id),
                -1,
            )
            expected_original = (
                original_ingredients[ingredient_index]
                if original_ingredients and 0 <= ingredient_index < len(original_ingredients) else None
            )
            if node.original_text != expected_original:
                errors.append(f"Ingredient original text differs from recipe: {node.id}")
        elif node.ingredient_id is not None:
            errors.append(f"Only ingredient nodes may have ingredient IDs: {node.id}")
        if node.type in {"intermediate", "final"} and len([edge for edge in incoming[node.id] if edge.type == "output"]) != 1:
            errors.append(f"Product needs exactly one producing operation: {node.id}")
        if node.type == "operation":
            if node.step_index is None or not 1 <= node.step_index <= len(steps):
                errors.append(f"Operation has invalid step index: {node.id}")
            elif node.source_instruction != steps[node.step_index - 1]:
                errors.append(f"Operation source instruction differs from recipe: {node.id}")
            else:
                source = steps[node.step_index - 1]
                if node.duration is not None and not duration_supported(node.duration, source):
                    errors.append(f"Duration is unsupported by source instruction: {node.id}")
                # Preheating may supply a later operation's explicitly stated heat.
                temperature_source = "\n".join(
                    [source, *(step for step in steps[:node.step_index - 1] if "preheat" in step.casefold())]
                )
                if node.temperature is not None and not temperature_supported(node.temperature, temperature_source):
                    errors.append(f"Temperature is unsupported by source instructions: {node.id}")
                if node.completion_condition and node.completion_condition.casefold() not in source.casefold():
                    errors.append(f"Completion condition differs from source instruction: {node.id}")
                equipment_source = " ".join(steps).casefold()
                inferred = {"bake": {"oven"}, "mix": {"bowl", "mixing bowl", "container"}}.get(node.action or "", set())
                for equipment in node.equipment:
                    if equipment.casefold() not in equipment_source and equipment.casefold() not in inferred:
                        errors.append(f"Equipment is unsupported by source instructions: {node.id}: {equipment}")

    for ingredient_id in expected.keys() - seen_ingredients:
        warnings.append(f"Missing source ingredient {ingredient_id}")
    if final_nodes:
        final_id = final_nodes[0].id
        reverse: dict[str, set[str]] = defaultdict(set)
        for source_id, targets in adjacency.items():
            for target_id in targets:
                reverse[target_id].add(source_id)
        reaches_final = {final_id}
        stack = [final_id]
        while stack:
            for source_id in reverse[stack.pop()]:
                if source_id not in reaches_final:
                    reaches_final.add(source_id)
                    stack.append(source_id)
        if not any(nodes[node_id].type == "ingredient" for node_id in reaches_final):
            errors.append("Final product is not reachable from an ingredient")
        for node in graph.nodes:
            if node.id not in reaches_final:
                warnings.append(f"Disconnected from final product: {node.id}")
            if node.type == "ingredient" and not outgoing[node.id]:
                warnings.append(f"Unused ingredient: {node.ingredient_id}")
    warnings.extend(f"Unresolved reference: {reference}" for reference in graph.unresolved_references)
    if errors:
        raise GraphValidationError(errors)
    return list(dict.fromkeys(warnings))
