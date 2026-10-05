"""Pure topology analysis shared by validation, compilation, and table views."""

from __future__ import annotations

from graphlib import CycleError, TopologicalSorter

from .canonical import CanonicalRecipe
from .semantic import SemanticRecipe


def get_operation_dependencies(semantic: SemanticRecipe) -> dict[str, set[str]]:
    ids = {op.id for op in semantic.operations}
    return {op.id: set(op.inputs) & ids for op in semantic.operations}


def topological_order(semantic: SemanticRecipe) -> list[str]:
    return list(TopologicalSorter(get_operation_dependencies(semantic)).static_order())


def is_acyclic(semantic: SemanticRecipe) -> bool:
    try:
        topological_order(semantic)
        return True
    except CycleError:
        return False


def get_terminal_operations(semantic: SemanticRecipe) -> list[str]:
    consumed = {ref for op in semantic.operations for ref in op.inputs}
    return [op.id for op in semantic.operations if op.id not in consumed]


def get_consumed_ingredients(semantic: SemanticRecipe) -> set[str]:
    return {ref for op in semantic.operations for ref in op.inputs if ref.startswith("ing_")} | {
        ref for prep in semantic.prep_actions for ref in prep.ingredients
    }


def get_unused_ingredients(canonical: CanonicalRecipe, semantic: SemanticRecipe) -> set[str]:
    return {item.id for item in canonical.ingredients} - get_consumed_ingredients(semantic)


def ingredient_groups(semantic: SemanticRecipe) -> dict[str, set[str]]:
    ops = {op.id: op for op in semantic.operations}
    groups: dict[str, set[str]] = {}
    for operation_id in topological_order(semantic):
        groups[operation_id] = set()
        for ref in ops[operation_id].inputs:
            groups[operation_id].update(groups[ref] if ref in groups else {ref})
    return groups


def is_laminar(semantic: SemanticRecipe) -> bool:
    if not is_acyclic(semantic):
        return False
    groups = list(ingredient_groups(semantic).values())
    if any(
        first & second and not (first <= second or second <= first)
        for index, first in enumerate(groups)
        for second in groups[index + 1 :]
    ):
        return False
    # A reserved stream used in multiple places requires the general TRN renderer.
    return all(
        sum(operation_id in op.inputs for op in semantic.operations) <= 1
        for operation_id in get_operation_dependencies(semantic)
    )


def can_render_as_table(semantic: SemanticRecipe) -> bool:
    return is_laminar(semantic) and len(get_terminal_operations(semantic)) == 1
