"""Minimal AI output: material operations refer to ingredients or earlier outputs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictInt

SEMANTIC_SCHEMA_VERSION = "1"
SEMANTIC_PROMPT_VERSION = "semantic-v1"
REPAIR_PROMPT_VERSION = "semantic-repair-v1"


class SourceParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: StrictInt
    action: str
    temperature: str | None
    duration: str | None
    heat_level: str | None
    equipment: list[str]
    completion_condition: str | None


class Portion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str
    text: str


class SemanticOperation(SourceParameters):
    id: str
    inputs: list[str]
    output_name: str | None
    portions: list[Portion]


class PrepAction(SourceParameters):
    # Recipe supplies are tracked without inventing material output from a pan.
    ingredients: list[str]


class SemanticRecipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prep_actions: list[PrepAction]
    operations: list[SemanticOperation]
    unresolved_references: list[str]
