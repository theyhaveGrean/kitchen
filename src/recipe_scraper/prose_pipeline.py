"""Optional downstream prose inference with a separate cache and source fallback."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .cache import cache_root, content_hash, read_record, write_record
from .canonical import CanonicalRecipe
from .llm import PROMPT_DIR, rewrite_instructions
from .presentation import PRESENTATION_VERSION, render_prose
from .semantic import SemanticRecipe


def faithful_prose(canonical: CanonicalRecipe, semantic: SemanticRecipe, steps: list[str]) -> bool:
    if len(steps) != len(canonical.instructions) or any(not step.strip() for step in steps):
        return False
    for source, candidate in zip(canonical.instructions, steps, strict=True):
        # Numeric quantities, units, conditions, equipment, and required actions
        # are checked conservatively. Unverifiable paraphrases retain the source.
        original = source.text.casefold()
        target = candidate.casefold()
        # Retaining the original numbers is insufficient if a rewrite also adds
        # a new time, temperature, or quantity. Reject new numeric tokens too.
        numbers = r"\d+(?:[./]\d+)?"
        if not set(re.findall(numbers, target)).issubset(re.findall(numbers, original)):
            return False
        numeric_phrases = re.findall(
            r"\d+(?:[./]\d+)?(?:\s*(?:[-–—]|to)\s*\d+(?:\.\d+)?)?\s*(?:°?[fc]|seconds?|minutes?|hours?|cups?|tbsp|tsp|inch(?:es)?)?",
            original,
        )
        if any(phrase.strip() not in target for phrase in numeric_phrases):
            return False
        for ingredient in canonical.ingredients:
            name = ingredient.name
            if name and name.casefold() in original and name.casefold() not in target:
                return False
        for operation in [*semantic.operations, *semantic.prep_actions]:
            if operation.step_index != source.index:
                continue
            for value in [
                operation.action,
                operation.duration,
                operation.temperature,
                operation.heat_level,
                operation.completion_condition,
                *operation.equipment,
            ]:
                if value and value.casefold() in original and value.casefold() not in target:
                    return False
    return True


def get_prose(
    canonical: CanonicalRecipe,
    semantic: SemanticRecipe,
    *,
    use_llm: bool = False,
    root: Path | None = None,
) -> list[str]:
    original = render_prose(canonical, semantic)
    if not use_llm:
        return original
    prompt = (PROMPT_DIR / "luna_recipe_rewrite.md").read_text(encoding="utf-8")
    key = content_hash(
        {
            "canonical": canonical.meaningful_content(),
            "semantic": semantic.model_dump(),
            "presentation": PRESENTATION_VERSION,
            "prompt": prompt,
            "model": os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        }
    )
    path = (root or cache_root()) / "prose" / f"{key}.json"
    cached = read_record(path, key)
    if (
        cached
        and isinstance(cached.get("steps"), list)
        and all(isinstance(step, str) for step in cached["steps"])
    ):
        if faithful_prose(canonical, semantic, cached["steps"]):
            return cached["steps"]
    try:
        candidate = rewrite_instructions(original, prompt)
        result = candidate if faithful_prose(canonical, semantic, candidate) else original
    except Exception:
        result = original
    write_record(
        path, {"cache_key": key, "steps": result, "used_source_fallback": result == original}
    )
    return result
