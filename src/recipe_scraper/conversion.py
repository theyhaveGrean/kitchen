"""Static extraction cache -> validated semantics -> deterministic presentation."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import (
    EXTRACTOR_VERSION,
    cache_root,
    content_hash,
    normalize_url,
    read_record,
    write_record,
)
from .canonical import CANONICAL_SCHEMA_VERSION, CanonicalRecipe, canonicalize
from .extractor import DEFAULT_TIMEOUT, extract_recipe
from .graph import RecipeGraph
from .graph_compile import build_recipe_graph
from .presentation import render_table
from .prose_pipeline import get_prose
from .semantic_pipeline import SemanticResult, get_semantic, semantic_cache_path


def extraction_cache_key(url: str) -> str:
    return content_hash(
        {
            "url": normalize_url(url),
            "extractor": EXTRACTOR_VERSION,
            "schema": CANONICAL_SCHEMA_VERSION,
        }
    )


def extract_canonical(
    url: str,
    *,
    root: Path | None = None,
    refresh: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    render_js: bool = False,
    auto_render_js: bool = True,
) -> CanonicalRecipe:
    root = root or cache_root()
    key = extraction_cache_key(url)
    path = root / "extraction" / f"{key}.json"
    ttl = float(os.getenv("RECIPE_EXTRACTION_CACHE_TTL", "86400"))
    record = None if refresh or render_js else read_record(path, key, ttl=ttl)
    if record is not None:
        try:
            canonical = CanonicalRecipe.model_validate(record["canonical"])
            canonical.metadata.update(
                extraction_cache_hit=True,
                timings={
                    "fetch_ms": 0,
                    "extract_ms": 0,
                    "browser_fallback_ms": 0,
                    "ingredient_parse_ms": 0,
                },
            )
            return canonical
        except (ValueError, KeyError, TypeError):
            pass
    recipe = extract_recipe(
        normalize_url(url), timeout=timeout, render_js=render_js, auto_render_js=auto_render_js
    )
    started = time.perf_counter()
    canonical = canonicalize(recipe)
    canonical.metadata.setdefault("timings", {})["ingredient_parse_ms"] = (
        time.perf_counter() - started
    ) * 1000
    canonical.metadata["extraction_cache_hit"] = False
    write_record(path, {"cache_key": key, "canonical": canonical.model_dump()})
    if canonical.canonical_url:
        alias = extraction_cache_key(canonical.canonical_url)
        write_record(
            root / "extraction" / f"{alias}.json",
            {"cache_key": alias, "canonical": canonical.model_dump()},
        )
    return canonical


@dataclass
class ConversionResult:
    canonical: CanonicalRecipe
    inference: SemanticResult
    graph: RecipeGraph
    prose: list[str]
    table: str | None
    timings: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical.model_dump(),
            "semantic": self.inference.semantic.model_dump(),
            "graph": self.graph.model_dump(),
            "presentation": self.canonical.product_json(self.prose),
            "issues": [issue.model_dump() for issue in self.inference.issues],
            "provenance": self.inference.provenance,
            "cache": {
                "semantic_hit": self.inference.cached,
                "extraction_hit": self.canonical.metadata.get("extraction_cache_hit", False),
            },
            "timings": self.timings,
        }


def convert_canonical(
    canonical: CanonicalRecipe,
    *,
    root: Path | None = None,
    refresh_semantic: bool = False,
    llm_prose: bool = False,
) -> ConversionResult:
    started = time.perf_counter()
    inference = get_semantic(
        canonical, semantic_cache_path(canonical, root), refresh=refresh_semantic
    )
    compile_start = time.perf_counter()
    graph = build_recipe_graph(canonical, inference.semantic)
    graph_ms = (time.perf_counter() - compile_start) * 1000
    prose_start = time.perf_counter()
    prose = get_prose(canonical, inference.semantic, root=root, use_llm=llm_prose)
    prose_ms = (time.perf_counter() - prose_start) * 1000
    table = render_table(canonical, inference.semantic)
    return ConversionResult(
        canonical,
        inference,
        graph,
        prose,
        table,
        {
            **inference.timings,
            "graph_compile_ms": graph_ms,
            "prose_render_ms": prose_ms,
            "total_ms": (time.perf_counter() - started) * 1000,
        },
    )


def convert_url(
    url: str,
    *,
    root: Path | None = None,
    refresh_extraction: bool = False,
    refresh_semantic: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> ConversionResult:
    started = time.perf_counter()
    canonical = extract_canonical(url, root=root, refresh=refresh_extraction, timeout=timeout)
    result = convert_canonical(canonical, root=root, refresh_semantic=refresh_semantic)
    result.timings.update(canonical.metadata.get("timings", {}))
    result.timings["total_ms"] = (time.perf_counter() - started) * 1000
    return result
