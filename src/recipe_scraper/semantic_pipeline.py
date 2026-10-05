"""Independent semantic cache, validation, one bounded repair, and provenance."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .cache import cache_root, content_hash, read_record, write_record
from .canonical import CanonicalRecipe
from .llm import REPAIR_PROMPT, SEMANTIC_PROMPT, infer_semantic_recipe, inference_tiers
from .semantic import (
    REPAIR_PROMPT_VERSION,
    SEMANTIC_PROMPT_VERSION,
    SEMANTIC_SCHEMA_VERSION,
    SemanticRecipe,
)
from .semantic_validation import ValidationIssue, has_errors, validate_semantic


class SemanticInferenceFailure(ValueError):
    def __init__(
        self, attempts: int, issues: list[ValidationIssue], last_output: SemanticRecipe | None
    ) -> None:
        self.attempts, self.issues, self.last_output = attempts, issues, last_output
        super().__init__(
            "; ".join(
                f"{issue.code}: {issue.message}" for issue in issues if issue.severity == "error"
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": "semantic",
            "attempts": self.attempts,
            "issues": [issue.model_dump() for issue in self.issues],
            "last_output": self.last_output.model_dump() if self.last_output is not None else None,
        }


@dataclass
class SemanticResult:
    semantic: SemanticRecipe
    issues: list[ValidationIssue]
    cached: bool
    provenance: dict[str, Any]
    timings: dict[str, float]


def semantic_cache_key(canonical: CanonicalRecipe) -> str:
    return content_hash(
        {
            "canonical": canonical.meaningful_content(),
            "schema": SEMANTIC_SCHEMA_VERSION,
            "schema_definition": SemanticRecipe.model_json_schema(),
            "prompt_version": SEMANTIC_PROMPT_VERSION,
            "repair_version": REPAIR_PROMPT_VERSION,
            "prompt": SEMANTIC_PROMPT.read_text(encoding="utf-8"),
            "repair_prompt": REPAIR_PROMPT.read_text(encoding="utf-8"),
            "tiers": [asdict(tier) for tier in inference_tiers()],
        }
    )


def semantic_cache_path(canonical: CanonicalRecipe, root: Path | None = None) -> Path:
    return (root or cache_root()) / "semantic" / f"{semantic_cache_key(canonical)}.json"


def load_semantic(canonical: CanonicalRecipe, path: Path) -> SemanticResult | None:
    started = time.perf_counter()
    record = read_record(path, semantic_cache_key(canonical))
    if record is None:
        return None
    try:
        semantic = SemanticRecipe.model_validate(record["semantic"])
        validation_started = time.perf_counter()
        issues = validate_semantic(canonical, semantic)
        if has_errors(issues):
            return None
        return SemanticResult(
            semantic,
            issues,
            True,
            record["provenance"],
            {
                "semantic_inference_ms": 0.0,
                "validation_ms": (time.perf_counter() - validation_started) * 1000,
                "repair_ms": 0.0,
                "semantic_cache_lookup_ms": (validation_started - started) * 1000,
            },
        )
    except (ValueError, TypeError, KeyError):
        return None


def get_semantic(
    canonical: CanonicalRecipe, path: Path | None = None, *, refresh: bool = False
) -> SemanticResult:
    path = path or semantic_cache_path(canonical)
    cached = None if refresh else load_semantic(canonical, path)
    if cached is not None:
        return cached
    primary, repair = inference_tiers()
    previous: SemanticRecipe | None = None
    timings = {"semantic_inference_ms": 0.0, "validation_ms": 0.0, "repair_ms": 0.0}
    issues: list[ValidationIssue] = []
    input_tokens = output_tokens = 0
    usage_complete = True
    actual_model = primary.model
    for index, tier in enumerate((primary, repair)):
        started = time.perf_counter()
        try:
            response = infer_semantic_recipe(
                canonical,
                tier,
                previous,
                [issue.model_dump() for issue in issues] if index else None,
            )
            previous = response.semantic
            input_tokens += response.input_tokens
            output_tokens += response.output_tokens
            actual_model = response.model
        except ValidationError as exc:
            issues = [ValidationIssue(code="INVALID_SCHEMA", message=str(exc))]
            usage_complete = False
            timings["repair_ms" if index else "semantic_inference_ms"] = (
                time.perf_counter() - started
            ) * 1000
        else:
            timings["repair_ms" if index else "semantic_inference_ms"] = (
                time.perf_counter() - started
            ) * 1000
            validation_start = time.perf_counter()
            issues = validate_semantic(canonical, previous)
            timings["validation_ms"] += (time.perf_counter() - validation_start) * 1000
        if not has_errors(issues) and previous is not None:
            provenance = {
                "generated_by_model": actual_model,
                "reasoning_effort": tier.reasoning_effort,
                "prompt_version": SEMANTIC_PROMPT_VERSION,
                "repair_prompt_version": REPAIR_PROMPT_VERSION,
                "semantic_schema_version": SEMANTIC_SCHEMA_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "validation_passed": True,
                "repair_attempts": index,
                "canonical_recipe_hash": content_hash(canonical.meaningful_content()),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "token_usage_complete": usage_complete,
            }
            write_record(
                path,
                {
                    "cache_key": semantic_cache_key(canonical),
                    "semantic": previous.model_dump(),
                    "provenance": provenance,
                    "issues": [issue.model_dump() for issue in issues],
                    "timings": timings,
                },
            )
            return SemanticResult(previous, issues, False, provenance, timings)
    raise SemanticInferenceFailure(2, issues, previous)
