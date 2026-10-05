"""Infer source semantics and compile presentation; no mandatory prose rewrite."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recipe_scraper.canonical import canonical_from_json  # noqa: E402
from recipe_scraper.conversion import convert_canonical  # noqa: E402
from recipe_scraper.graph_pipeline import get_or_generate_graph  # noqa: E402
from recipe_scraper.semantic_pipeline import SemanticInferenceFailure  # noqa: E402


def files_from_summary(summary: Path, input_dir: Path) -> list[Path]:
    with summary.open(encoding="utf-8-sig", newline="") as file:
        files = [
            Path(row["json_file"]).resolve()
            for row in csv.DictReader(file)
            if row.get("status") == "success" and row.get("json_file")
        ]
    if any(path.parent != input_dir.resolve() for path in files):
        raise ValueError("Summary JSON must be inside the selected input directory")
    return files


def process_file(path: Path, output_dir: Path) -> None:
    source_path = path.parent.parent / "canonical" / path.name
    data = json.loads((source_path if source_path.exists() else path).read_text(encoding="utf-8"))
    canonical = canonical_from_json(data)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / path.name
    try:
        result = convert_canonical(canonical)
    except SemanticInferenceFailure as exc:
        target.write_text(
            json.dumps(canonical.product_json(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        failure_path = output_dir.parent / "failures" / path.name
        failure_path.parent.mkdir(parents=True, exist_ok=True)
        failure_path.write_text(
            json.dumps(exc.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        raise
    target.write_text(
        json.dumps(canonical.product_json(result.prose), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifact = output_dir.parent / "semantic" / path.name
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    graph, warnings, cached = get_or_generate_graph(
        output_dir.parent / "graphs" / path.name, canonical.model_dump()
    )
    print(
        f"Semantic {path.name}: {len(result.inference.semantic.operations)} operations, "
        f"{len(warnings)} warnings, {len(graph.nodes)} compiled nodes{' (cached)' if cached else ''}"
    )
    print(f"{path.name} -> {target}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "benchmarks/results/latest")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "benchmarks/results/rewritten")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    if args.input_dir.resolve() == args.output_dir.resolve():
        parser.error("Input and output directories must differ")
    files = (
        files_from_summary(args.summary, args.input_dir)
        if args.summary
        else sorted(args.input_dir.glob("*.json"))
    )
    failures = 0
    for index, path in enumerate(files, 1):
        print(f"[{index}/{len(files)}] Inferring {path.name}", flush=True)
        try:
            process_file(path, args.output_dir)
        except Exception as exc:
            failures += 1
            print(f"FAILED: {path.name}: {exc}", flush=True)
    print(f"Semantic conversion completed: {len(files) - failures} passed, {failures} failed")
    return int(bool(failures or not files))


if __name__ == "__main__":
    raise SystemExit(main())
