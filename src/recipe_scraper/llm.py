"""Single boundary for OpenAI calls and model configuration."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .graph import RecipeGraph

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
GRAPH_PROMPT = PROMPT_DIR / "luna_recipe_graph.md"


def _client() -> Any:
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv()
    return OpenAI()


def graph_model() -> str:
    from dotenv import load_dotenv

    load_dotenv()
    return os.getenv("OPENAI_GRAPH_MODEL", "gpt-5.6-luna")


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


def generate_recipe_graph(
    recipe_input: dict[str, Any], previous_graph: RecipeGraph | None = None,
    validation_errors: list[str] | None = None,
) -> RecipeGraph:
    """Ask Luna for semantic flow using the SDK's strict Pydantic output format."""
    messages = [
        {"role": "system", "content": GRAPH_PROMPT.read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(recipe_input, ensure_ascii=False, separators=(",", ":"))},
    ]
    if previous_graph is not None and validation_errors:
        messages.append({
            "role": "user",
            "content": (
                "The previous graph failed deterministic validation. Regenerate the complete graph "
                "without inventing uncertain dependencies. Errors: "
                f"{json.dumps(validation_errors)}. Previous graph: "
                f"{previous_graph.model_dump_json()}"
            ),
        })
    response = _client().responses.parse(
        model=graph_model(),
        input=messages,
        text_format=RecipeGraph,
    )
    if response.status != "completed" or response.output_parsed is None:
        raise ValueError(f"Graph generation did not return a complete structured graph: {response.status}")
    return response.output_parsed
