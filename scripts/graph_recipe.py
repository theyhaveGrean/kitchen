"""Generate or reuse a graph for a saved structured recipe."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recipe_scraper.graph_pipeline import (  # noqa: E402
    get_or_generate_graph,
    source_ingredient_lines,
)
from recipe_scraper.graph_render import graph_debug_text, render_svg  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recipe", type=Path, help="Structured recipe JSON")
    parser.add_argument("--source", type=Path, help="Extraction JSON with original ingredient lines")
    parser.add_argument("--output", type=Path, help="Graph cache JSON path")
    parser.add_argument("--svg", type=Path, help="Write a standalone SVG preview")
    args = parser.parse_args()
    try:
        recipe = json.loads(args.recipe.read_text(encoding="utf-8"))
        original = source_ingredient_lines(json.loads(args.source.read_text(encoding="utf-8"))) if args.source else None
        output = args.output or ROOT / "benchmarks/results/graphs" / args.recipe.name
        graph, warnings, cached = get_or_generate_graph(output, recipe, original)
        if args.svg:
            args.svg.parent.mkdir(parents=True, exist_ok=True)
            args.svg.write_text(render_svg(graph), encoding="utf-8")
        print(f"{output} ({'cached' if cached else 'generated'})")
        print(graph_debug_text(graph))
        for warning in warnings:
            print(f"VALIDATION WARNING: {warning}")
        return 0
    except Exception as exc:
        print(f"Graph generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
