"""Single boundary for OpenAI calls and model configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import CanonicalRecipe
from .semantic import SemanticRecipe

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
SEMANTIC_PROMPT = PROMPT_DIR / "semantic_recipe.md"
REPAIR_PROMPT = PROMPT_DIR / "semantic_repair.md"


@dataclass(frozen=True)
class ModelTier:
    model: str
    reasoning_effort: str


def inference_tiers() -> tuple[ModelTier, ModelTier]:
    from dotenv import load_dotenv

    load_dotenv()
    primary = ModelTier(
        os.getenv("OPENAI_SEMANTIC_MODEL", os.getenv("OPENAI_GRAPH_MODEL", "gpt-5.6-luna")),
        os.getenv("OPENAI_SEMANTIC_REASONING", "low"),
    )
    repair = ModelTier(
        os.getenv("OPENAI_REPAIR_MODEL", primary.model),
        os.getenv("OPENAI_REPAIR_REASONING", "medium"),
    )
    return primary, repair


@dataclass
class SemanticResponse:
    semantic: SemanticRecipe
    model: str
    reasoning_effort: str
    input_tokens: int = 0
    output_tokens: int = 0


def semantic_input(canonical: CanonicalRecipe) -> dict[str, Any]:
    return {
        "title": canonical.title,
        "ingredients": [
            {"id": item.id, "text": item.original_text} for item in canonical.ingredients
        ],
        "instructions": [
            {"index": step.index, "text": step.text} for step in canonical.instructions
        ],
    }


def _client() -> Any:
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    return OpenAI(max_retries=0)


def graph_model() -> str:
    """Compatibility name; graph construction itself no longer uses a model."""
    return inference_tiers()[0].model


def rewrite_instructions(instructions: list[str], prompt: str) -> list[str]:
    response = _client().responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        reasoning={"effort": "none"},
        input=(
            f"{prompt}\n\n## Recipe\n\nRewrite the following recipe instructions.\n"
            "Return ONLY a valid JSON array of strings. Keep the same logical step order.\n\n"
            f"{json.dumps(instructions, ensure_ascii=False, indent=2)}"
        ),
    )
    rewritten = json.loads(response.output_text.strip())
    if not isinstance(rewritten, list) or not all(isinstance(step, str) for step in rewritten):
        raise ValueError("Model output must be a JSON array of instruction strings")
    return rewritten


def infer_semantic_recipe(
    canonical: CanonicalRecipe,
    tier: ModelTier,
    previous: SemanticRecipe | None = None,
    issues: list[dict[str, Any]] | None = None,
) -> SemanticResponse:
    """The sole structured inference API boundary; never emits a RecipeGraph."""
    messages = [
        {"role": "system", "content": SEMANTIC_PROMPT.read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": json.dumps(
                semantic_input(canonical), ensure_ascii=False, separators=(",", ":")
            ),
        },
    ]
    if issues:
        messages.append(
            {
                "role": "user",
                "content": REPAIR_PROMPT.read_text(encoding="utf-8")
                + "\nIssues: "
                + json.dumps(issues, ensure_ascii=False)
                + ("\nPrevious: " + previous.model_dump_json() if previous is not None else ""),
            }
        )
    response = _client().responses.parse(
        model=tier.model,
        reasoning={"effort": tier.reasoning_effort},
        input=messages,
        text_format=SemanticRecipe,
    )
    if response.status != "completed" or response.output_parsed is None:
        raise ValueError(
            f"Semantic generation did not return a complete structured recipe: {response.status}"
        )
    return SemanticResponse(
        response.output_parsed,
        response.model,
        tier.reasoning_effort,
        response.usage.input_tokens if response.usage else 0,
        response.usage.output_tokens if response.usage else 0,
    )
