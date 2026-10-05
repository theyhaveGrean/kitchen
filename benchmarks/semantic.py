"""Evaluate saved canonical inputs offline or against real configured model tiers."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recipe_scraper.canonical import canonical_from_json  # noqa: E402
from recipe_scraper.conversion import convert_canonical  # noqa: E402
from recipe_scraper.graph_compile import build_recipe_graph  # noqa: E402
from recipe_scraper.graph_render import render_svg  # noqa: E402
from recipe_scraper.semantic import SemanticRecipe  # noqa: E402
from recipe_scraper.semantic_pipeline import SemanticInferenceFailure  # noqa: E402
from recipe_scraper.semantic_topology import get_consumed_ingredients  # noqa: E402
from recipe_scraper.semantic_validation import has_errors, validate_semantic  # noqa: E402


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    good = [row for row in rows if row["success"]]
    latencies = sorted(row["elapsed_ms"] for row in rows)
    return {
        "cases": len(rows),
        "successes": len(good),
        "success_rate": len(good) / len(rows) if rows else 0,
        "median_ms": statistics.median(latencies) if latencies else None,
        "p90_ms": latencies[min(len(latencies) - 1, int((len(latencies) - 1) * 0.9 + 0.5))]
        if latencies
        else None,
        "output_tokens": sum(
            row.get("api_output_tokens", row.get("output_tokens", 0)) for row in rows
        ),
        "repair_rate": sum(row.get("repair_attempts", 0) > 0 for row in rows) / len(rows)
        if rows
        else 0,
        "mean_ingredient_coverage": statistics.mean(row["ingredient_coverage"] for row in good)
        if good
        else None,
        "temperature_grounding_failures": sum(
            row.get("temperature_grounding_failures", 0) for row in rows
        ),
        "duration_grounding_failures": sum(
            row.get("duration_grounding_failures", 0) for row in rows
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use real API; otherwise validate saved expected semantics",
    )
    parser.add_argument("--dataset", type=Path)
    parser.add_argument(
        "--input-dir", type=Path, help="Saved CanonicalRecipe JSON; never re-fetch pages"
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results/semantic.json")
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    dataset = (
        args.dataset or ROOT / f"tests/fixtures/{'graph' if args.live else 'semantic'}_cases.json"
    )
    cases = (
        [
            {"case": path.stem, "recipe": json.loads(path.read_text(encoding="utf-8"))}
            for path in sorted(args.input_dir.glob("*.json"))
        ]
        if args.input_dir
        else json.loads(dataset.read_text(encoding="utf-8"))
    )
    if args.limit is not None:
        cases = cases[: args.limit]
    rows: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        row: dict[str, Any] = {"case": case["case"], "success": False, "live": args.live}
        try:
            canonical = canonical_from_json(case["recipe"])
            if args.live:
                result = convert_canonical(
                    canonical, root=args.cache_dir, refresh_semantic=args.refresh
                )
                semantic, graph = result.inference.semantic, result.graph
                row.update(
                    result.inference.provenance,
                    cache_hit=result.inference.cached,
                    timings=result.timings,
                )
                row["api_output_tokens"] = (
                    0 if result.inference.cached else result.inference.provenance["output_tokens"]
                )
                row["api_input_tokens"] = (
                    0 if result.inference.cached else result.inference.provenance["input_tokens"]
                )
            else:
                semantic = SemanticRecipe.model_validate(case["semantic"])
                issues = validate_semantic(canonical, semantic)
                if has_errors(issues):
                    raise SemanticInferenceFailure(0, issues, semantic)
                graph = build_recipe_graph(canonical, semantic)
            svg = render_svg(graph)
            assert "<svg" in svg
            row.update(
                success=True,
                semantic_bytes=len(semantic.model_dump_json().encode("utf-8")),
                graph_bytes=len(graph.model_dump_json().encode("utf-8")),
                ingredient_coverage=len(get_consumed_ingredients(semantic))
                / len(canonical.ingredients),
            )
        except SemanticInferenceFailure as exc:
            row.update(
                error=exc.as_dict(),
                repair_attempts=max(0, exc.attempts - 1),
                temperature_grounding_failures=sum(
                    issue.code == "INVENTED_TEMPERATURE" for issue in exc.issues
                ),
                duration_grounding_failures=sum(
                    issue.code == "INVENTED_DURATION" for issue in exc.issues
                ),
            )
        except Exception as exc:
            row["error"] = str(exc)
        row["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
        print(case["case"], "PASS" if row["success"] else "FAIL", row["elapsed_ms"], flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"summary": summarize(rows), "cases": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(summarize(rows), indent=2))
    return int(any(not row["success"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
