"""Inspect every stage independently, including entirely offline graph compilation."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .cache import write_record
from .canonical import CanonicalRecipe, canonical_from_json, canonicalize
from .conversion import convert_canonical, extract_canonical
from .extractor import extract_from_html
from .graph_compile import build_recipe_graph
from .graph_render import render_svg
from .presentation import render_table
from .semantic import SemanticRecipe
from .semantic_pipeline import SemanticInferenceFailure
from .semantic_validation import has_errors, validate_semantic


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Input JSON must be an object")
    return data


def load_source(path: Path) -> CanonicalRecipe:
    return canonical_from_json(load_json(path))


def _emit(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="stage", required=True)
    for name in ("extract", "infer", "validate", "graph", "convert"):
        sub = subs.add_parser(name)
        sub.add_argument("source")
        sub.add_argument("-o", "--output", type=Path)
        if name in {"extract", "convert"}:
            sub.add_argument("--html-file", action="store_true")
            sub.add_argument("--timeout", type=int, default=60)
            sub.add_argument("--refresh-extraction", action="store_true")
        if name in {"extract", "infer", "convert"}:
            sub.add_argument("--cache-dir", type=Path)
        if name in {"infer", "convert"}:
            sub.add_argument("--refresh-semantic", action="store_true")
            sub.add_argument(
                "--llm-prose",
                action="store_true",
                help="Optional downstream rewrite with independent caching and source fallback",
            )
        if name in {"graph", "validate"}:
            sub.add_argument(
                "--canonical", type=Path, help="Canonical JSON when SOURCE contains only semantics"
            )
        if name in {"graph", "convert", "infer"}:
            sub.add_argument("--svg", type=Path)
            sub.add_argument("--table", type=Path)
    args = parser.parse_args(argv)
    canonical: CanonicalRecipe | None = None
    try:
        started = time.perf_counter()
        if args.stage in {"extract", "convert"}:
            if args.html_file:
                path = Path(args.source).resolve()
                recipe = extract_from_html(path.read_text(encoding="utf-8"), path.as_uri())
                if recipe is None:
                    raise ValueError("No recipe in HTML fixture")
                canonical = canonicalize(recipe)
            else:
                canonical = extract_canonical(
                    args.source,
                    root=args.cache_dir,
                    timeout=args.timeout,
                    refresh=args.refresh_extraction,
                )
            if args.stage == "extract":
                _emit(canonical.model_dump(), args.output)
                return 0
        elif args.stage == "infer":
            canonical = load_source(Path(args.source))
        else:
            data = load_json(Path(args.source))
            canonical = (
                load_source(args.canonical)
                if args.canonical
                else CanonicalRecipe.model_validate(data["canonical"])
            )
            semantic = SemanticRecipe.model_validate(data.get("semantic", data))
            issues = validate_semantic(canonical, semantic)
            if args.stage == "validate":
                _emit(
                    {
                        "valid": not has_errors(issues),
                        "issues": [issue.model_dump() for issue in issues],
                    },
                    args.output,
                )
                return int(has_errors(issues))
            graph = build_recipe_graph(canonical, semantic)
            _emit(graph.model_dump(), args.output)
            if args.svg:
                args.svg.parent.mkdir(parents=True, exist_ok=True)
                args.svg.write_text(render_svg(graph), encoding="utf-8")
            if args.table:
                table = render_table(canonical, semantic)
                if table is None:
                    raise ValueError("Nonlaminar material flow: use --svg instead of a table")
                args.table.parent.mkdir(parents=True, exist_ok=True)
                args.table.write_text(table, encoding="utf-8")
            return 0
        assert canonical is not None
        result = convert_canonical(
            canonical,
            root=args.cache_dir,
            refresh_semantic=args.refresh_semantic,
            llm_prose=args.llm_prose,
        )
        result.timings.update(canonical.metadata.get("timings", {}))
        result.timings["total_ms"] = (time.perf_counter() - started) * 1000
        _emit(result.as_dict(), args.output)
        if args.svg:
            args.svg.parent.mkdir(parents=True, exist_ok=True)
            args.svg.write_text(render_svg(result.graph), encoding="utf-8")
        if args.table and result.table is not None:
            args.table.parent.mkdir(parents=True, exist_ok=True)
            args.table.write_text(result.table, encoding="utf-8")
        return 0
    except SemanticInferenceFailure as exc:
        failure = exc.as_dict()
        if canonical is not None:
            failure["canonical"] = canonical.model_dump()
            failure["presentation"] = canonical.product_json()
        _emit(failure, args.output)
        return 1
    except Exception as exc:
        print(f"{args.stage} failed: {exc}", file=sys.stderr)
        return 1


def save_conversion(path: Path, result: dict[str, Any]) -> None:
    """Sidecar artifacts keep provenance out of semantic/product objects."""
    write_record(path, result)
