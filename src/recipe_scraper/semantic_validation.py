"""Structured validation of AI semantics against immutable source data."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .canonical import CanonicalRecipe
from .graph import is_material_label
from .graph_measurements import (
    duration_supported,
    parse_duration,
    parse_temperature,
    temperature_supported,
)
from .semantic import SemanticRecipe, SourceParameters
from .semantic_topology import get_terminal_operations, get_unused_ingredients, is_acyclic


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    operation_id: str | None = None
    ingredient_id: str | None = None
    severity: Literal["error", "warning"] = "error"


def has_errors(issues: list[ValidationIssue]) -> bool:
    return any(issue.severity == "error" for issue in issues)


def _text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def validate_semantic(
    canonical: CanonicalRecipe, semantic: SemanticRecipe
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    ingredients = {item.id: item for item in canonical.ingredients}
    positions = {op.id: index for index, op in enumerate(semantic.operations)}
    seen: set[str] = set()
    duplicate_keys: set[tuple[object, ...]] = set()

    def add(
        code: str,
        message: str,
        operation_id: str | None = None,
        ingredient_id: str | None = None,
        severity: Literal["error", "warning"] = "error",
    ) -> None:
        issues.append(
            ValidationIssue(
                code=code,
                message=message,
                operation_id=operation_id,
                ingredient_id=ingredient_id,
                severity=severity,
            )
        )

    def parameters(op: SourceParameters, operation_id: str) -> None:
        if not 1 <= op.step_index <= len(canonical.instructions):
            add("INVALID_STEP_INDEX", "Step does not exist in source instructions", operation_id)
            return
        source = canonical.instructions[op.step_index - 1].text
        action = op.action
        if (
            action != action.lower()
            or len(action) > 30
            or len(action.split()) > 4
            or not all(word.isalpha() for word in action.replace("-", " ").split())
            or not action.strip()
            or action.split()[0]
            in {
                "until",
                "oven",
                "bowl",
                "pan",
                "temperature",
                "duration",
                "golden",
                "tender",
                "smooth",
            }
        ):
            add(
                "ACTION_TOO_VERBOSE",
                "Use a concise cooking verb, not instructions or metadata",
                operation_id,
            )
        if op.duration:
            parsed = parse_duration(op.duration)
            if (
                _text(op.duration) not in _text(source) and parsed.unit is None
            ) or not duration_supported(parsed, source):
                add(
                    "INVENTED_DURATION", "Duration lacks evidence in this source step", operation_id
                )
        if op.temperature:
            parsed_temperature = parse_temperature(op.temperature)
            prior_preheats = [
                step.text
                for step in canonical.instructions[: op.step_index - 1]
                if "preheat" in step.text.lower()
            ]
            evidence = "\n".join([source, *prior_preheats])
            if parsed_temperature.unit is None or not temperature_supported(
                parsed_temperature, evidence
            ):
                add(
                    "INVENTED_TEMPERATURE",
                    "Temperature lacks source evidence; internal targets are completion criteria",
                    operation_id,
                )
        for equipment in op.equipment:
            if not equipment.strip() or _text(equipment) not in _text(
                " ".join(step.text for step in canonical.instructions)
            ):
                add("INVENTED_EQUIPMENT", f"Equipment is not stated: {equipment}", operation_id)
        for field in (op.heat_level, op.completion_condition):
            if field is not None and (not field.strip() or _text(field) not in _text(source)):
                add(
                    "INVENTED_CONDITION",
                    "Heat/completion condition must come from this source step",
                    operation_id,
                )

    for index, op in enumerate(semantic.operations):
        if op.id in seen:
            add("DUPLICATE_OPERATION_ID", "Operation ID was already used", op.id)
        seen.add(op.id)
        if op.id != f"op_{index + 1:03d}":
            add(
                "INVALID_OPERATION_ID",
                "Operation IDs must follow array order: op_001, op_002, ...",
                op.id,
            )
        parameters(op, op.id)
        if not op.inputs:
            add(
                "EMPTY_INPUTS",
                "Material operation needs material inputs; environmental actions belong in prep_actions",
                op.id,
            )
        if len(op.inputs) != len(set(op.inputs)):
            add("DUPLICATE_INPUT", "Use each material reference once per operation", op.id)
        for ref in op.inputs:
            if ref in ingredients:
                continue
            if ref not in positions:
                add(
                    "UNKNOWN_INGREDIENT" if ref.startswith("ing_") else "UNKNOWN_OPERATION",
                    f"Unknown material: {ref}",
                    op.id,
                )
            elif positions[ref] >= index:
                add("FORWARD_REFERENCE", f"Input must reference an earlier operation: {ref}", op.id)
            elif semantic.operations[positions[ref]].step_index > op.step_index:
                add("TEMPORAL_ORDER", "Material cannot be produced by a later source step", op.id)
        key = (
            op.step_index,
            op.action,
            tuple(op.inputs),
            op.temperature,
            op.duration,
            op.completion_condition,
        )
        if key in duplicate_keys:
            add(
                "SUSPICIOUS_DUPLICATE_OPERATION",
                "Identical action and material already modeled in this step",
                op.id,
            )
        duplicate_keys.add(key)
        portion_refs: set[str] = set()
        for portion in op.portions:
            if portion.ref not in op.inputs or portion.ref in portion_refs:
                add("INVALID_PORTION", "Portion must identify one unique input", op.id)
            portion_refs.add(portion.ref)
            evidence = " ".join(
                [
                    *(step.text for step in canonical.instructions),
                    *(item.original_text for item in canonical.ingredients),
                ]
            )
            if not portion.text.strip() or _text(portion.text) not in _text(evidence):
                add("INVENTED_PORTION", "Portion must retain source wording", op.id)
        if op.output_name is not None and (
            not is_material_label(op.output_name) or len(op.output_name) > 80
        ):
            add(
                "INVALID_OUTPUT_NAME", "Output should name a concise actual cooking material", op.id
            )
    for index, prep in enumerate(semantic.prep_actions, 1):
        prep_id = f"prep_{index:03d}"
        parameters(prep, prep_id)
        if prep.action in {
            "mix",
            "fold",
            "whisk",
            "knead",
            "bake",
            "fry",
            "roast",
            "marinate",
            "simmer",
        }:
            add("INVALID_PREP_ACTION", "Material transformation belongs in operations", prep_id)
        for ingredient_id in prep.ingredients:
            if ingredient_id not in ingredients:
                add(
                    "UNKNOWN_INGREDIENT",
                    "Prep supply is not a canonical ingredient",
                    prep_id,
                    ingredient_id,
                )
    if not is_acyclic(semantic):
        add("CYCLE", "Material references contain a cycle")
    terminals = get_terminal_operations(semantic)
    if len(terminals) != 1:
        add(
            "NO_TERMINAL" if not terminals else "MULTIPLE_TERMINALS",
            "Exactly one terminal material output is required; do not fabricate a merge",
        )
    for ingredient_id in sorted(get_unused_ingredients(canonical, semantic)):
        optional = bool(
            re.search(
                r"optional|for (?:garnish|serving|greasing|dusting)|cooking spray",
                ingredients[ingredient_id].original_text,
                re.I,
            )
        )
        add(
            "UNUSED_INGREDIENT",
            "Source ingredient is not used; preserve it in the canonical view",
            ingredient_id=ingredient_id,
            severity="warning" if optional or semantic.unresolved_references else "error",
        )
    for reference in semantic.unresolved_references:
        add("UNRESOLVED_REFERENCE", reference, severity="warning")
    return issues
