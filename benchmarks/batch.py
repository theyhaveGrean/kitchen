#!/usr/bin/env python3
"""Batch/regression runner for the recipe_scraper package.

Supports both project CSV formats:

Legacy URL set::
    id,site,recipe_name,category,url

Torture set::
    id,test_kind,site,title,content_type,url_or_fixture,...

Fixture rows are run with ``--html-file``. Rows whose expected outcome is
``reject`` pass when the extractor correctly rejects the page.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value.strip())
    return cleaned.strip("._") or "recipe"


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        if "id" not in fields:
            raise ValueError("CSV is missing required column: id")
        if not ({"url", "url_or_fixture"} & fields):
            raise ValueError("CSV needs either 'url' or 'url_or_fixture'")

        rows: list[dict[str, str]] = []
        for line_number, raw in enumerate(reader, start=2):
            row = {str(k): (v or "").strip() for k, v in raw.items() if k is not None}
            source = row.get("url") or row.get("url_or_fixture")
            if not source:
                print(f"Skipping CSV line {line_number}: empty source", file=sys.stderr)
                continue
            row["source"] = source
            row["recipe_name"] = row.get("recipe_name") or row.get("title") or row["id"]
            row.setdefault("site", "")
            row.setdefault("category", "")
            row.setdefault("test_kind", "live")
            row.setdefault("expected_outcome", "pass")
            rows.append(row)
    return rows


def parse_json(stdout: str) -> dict[str, Any]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError("extractor output is not a JSON object")
    return payload


def public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only the product-facing recipe schema in saved JSON files."""
    return {key: payload.get(key) for key in ("title", "link", "ingredients", "recipe")}


def allowed_methods(row: dict[str, str]) -> set[str]:
    raw = row.get("allowed_methods") or row.get("expected_method") or "any"
    return {x.strip() for x in raw.split("|") if x.strip()}



def normalize_title_tokens(value: str) -> list[str]:
    """Normalize a title for benchmark comparison, not product output.

    Publishers frequently prepend adjectives ("Easy"), append clarifiers
    ("/ Risoni Pasta"), or add the generic word "recipe" without changing
    which recipe the page represents.
    """
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return [token for token in normalized.split() if token != "recipe"]


def titles_compatible(expected: str, actual: str) -> bool:
    if not expected or not actual:
        return expected.strip() == actual.strip()
    expected_tokens = normalize_title_tokens(expected)
    actual_tokens = normalize_title_tokens(actual)
    if expected_tokens == actual_tokens:
        return True
    # The benchmark title is an identity check, not an exact-copy requirement.
    # Accept publisher-added qualifiers while requiring every expected token.
    return bool(expected_tokens) and set(expected_tokens).issubset(set(actual_tokens))

def meets_expectations(row: dict[str, str], payload: dict[str, Any]) -> tuple[bool, str]:
    ingredients = payload.get("ingredients") if isinstance(payload.get("ingredients"), list) else []
    steps = payload.get("recipe") if isinstance(payload.get("recipe"), list) else []
    debug = payload.get("_debug") if isinstance(payload.get("_debug"), dict) else {}

    min_ingredients = int(row.get("min_ingredients") or 0)
    min_steps = int(row.get("min_instructions") or 0)
    if len(ingredients) < min_ingredients:
        return False, f"expected >= {min_ingredients} ingredients, got {len(ingredients)}"
    if len(steps) < min_steps:
        return False, f"expected >= {min_steps} steps, got {len(steps)}"

    expected_title = row.get("expected_title", "")
    actual_title = (payload.get("title") or "").strip()
    if expected_title and not titles_compatible(expected_title, actual_title):
        return False, f"expected title compatible with {expected_title!r}, got {actual_title!r}"

    methods = allowed_methods(row)
    method = str(debug.get("extraction_method") or "")
    if methods and "any" not in methods and "none" not in methods and method not in methods:
        return False, f"expected method {'|'.join(sorted(methods))}, got {method or '<none>'}"
    return True, ""


def run_one(
    row: dict[str, str], *, project_root: Path, python_executable: str,
    output_dir: Path, timeout: int,
) -> dict[str, Any]:
    recipe_id = safe_filename(row["id"])
    output_json = output_dir / f"{recipe_id}.json"
    is_fixture = row.get("test_kind", "").casefold() == "fixture"
    source = row["source"]
    if is_fixture:
        source_path = Path(source)
        if not source_path.is_absolute():
            csv_relative = (Path(row["_csv_dir"]) / source_path).resolve()
            repo_relative = (project_root / source_path).resolve()
            source_path = csv_relative if csv_relative.exists() else repo_relative
        source = str(source_path)
        if not source_path.exists():
            result = {
                "id": row.get("id", ""), "site": row.get("site", ""),
                "recipe_name": row.get("recipe_name", ""), "source": row.get("source", ""),
                "expected_outcome": row.get("expected_outcome", "pass"), "status": "failed",
                "exit_code": "", "extraction_method": "", "ingredient_count": "",
                "instruction_count": "", "title_extracted": "", "elapsed_seconds": "0.000",
                "json_file": "", "error": f"Fixture not found: {source_path}",
            }
            return result

    cmd = [python_executable, "-m", "recipe_scraper", source, "--timeout", str(timeout), "--debug-metadata"]
    if is_fixture:
        cmd.append("--html-file")

    result: dict[str, Any] = {
        "id": row.get("id", ""), "site": row.get("site", ""),
        "recipe_name": row.get("recipe_name", ""), "source": row.get("source", ""),
        "expected_outcome": row.get("expected_outcome", "pass"),
        "status": "failed", "exit_code": "", "extraction_method": "",
        "ingredient_count": "", "instruction_count": "", "title_extracted": "",
        "elapsed_seconds": "", "json_file": "", "error": "",
    }

    env = os.environ.copy()
    src_dir = str(project_root / "src")
    env["PYTHONPATH"] = src_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    started = time.perf_counter()
    hard_timeout = max(timeout + 10, 30) if timeout > 0 else None

    try:
        proc = subprocess.run(
            cmd, text=True, capture_output=True, encoding="utf-8", errors="replace",
            env=env, timeout=hard_timeout,
        )
    except subprocess.TimeoutExpired:
        result["elapsed_seconds"] = f"{time.perf_counter() - started:.3f}"
        result["error"] = f"Hard timeout: extractor exceeded {hard_timeout}s"
        return result

    result["exit_code"] = proc.returncode
    result["elapsed_seconds"] = f"{time.perf_counter() - started:.3f}"
    expected_reject = row.get("expected_outcome", "pass").casefold() in {"reject", "reject_or_unsupported"}

    if proc.returncode != 0:
        if expected_reject:
            result["status"] = "success"
            result["error"] = "Correctly rejected non-recipe input"
            return result
        result["error"] = (proc.stderr or proc.stdout or "Unknown extractor error").strip()[-4000:]
        return result

    if expected_reject:
        result["error"] = "Expected rejection, but extractor returned a recipe"
        return result

    try:
        payload = parse_json(proc.stdout)
    except Exception as exc:
        result["error"] = f"Could not parse extractor JSON: {exc}"
        return result

    ok, expectation_error = meets_expectations(row, payload)
    debug = payload.get("_debug") if isinstance(payload.get("_debug"), dict) else {}
    ingredients = payload.get("ingredients") if isinstance(payload.get("ingredients"), list) else []
    steps = payload.get("recipe") if isinstance(payload.get("recipe"), list) else []
    result.update({
        "status": "success" if ok else "failed",
        "extraction_method": debug.get("extraction_method", ""),
        "ingredient_count": len(ingredients), "instruction_count": len(steps),
        "title_extracted": payload.get("title") or "", "error": expectation_error,
    })
    if ok:
        output_json.write_text(json.dumps(public_payload(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["json_file"] = str(output_json)
    return result


def write_summary(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "id", "site", "recipe_name", "source", "expected_outcome", "status",
        "exit_code", "extraction_method", "ingredient_count", "instruction_count",
        "title_extracted", "elapsed_seconds", "json_file", "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(results)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Batch-test recipe extraction from CSV URLs or fixtures.")
    parser.add_argument("csv_file", nargs="?", default=str(project_root / "benchmarks/datasets/recipes_100.csv"))
    parser.add_argument("--output-dir", default=str(project_root / "benchmarks/results/latest"))
    parser.add_argument("--timeout", type=int, default=60, help="Per-page Scrapling timeout in seconds; 0 disables it")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--start", type=int, default=1, help="1-based first dataset row to run")
    parser.add_argument("--limit", type=int, help="Maximum number of dataset rows to run")
    args = parser.parse_args()

    if args.start < 1 or (args.limit is not None and args.limit < 1):
        parser.error("--start and --limit must be positive")

    csv_path = Path(args.csv_file).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not csv_path.exists():
        print(f"Missing input: {csv_path}", file=sys.stderr)
        return 2
    try:
        rows = load_rows(csv_path)
    except Exception as exc:
        print(f"Could not read test CSV: {exc}", file=sys.stderr)
        return 2
    rows = rows[args.start - 1:]
    if args.limit is not None:
        rows = rows[:args.limit]
    if not rows:
        print("No test rows selected.", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        row["_csv_dir"] = str(csv_path.parent)

    print(f"Testing {len(rows)} recipes from {csv_path.name}")
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        print(f"[{index}/{len(rows)}] {row.get('site','')}: {row['recipe_name']}")
        result = run_one(
            row, project_root=project_root, python_executable=args.python,
            output_dir=output_dir, timeout=args.timeout,
        )
        results.append(result)
        print(f"  {result['status'].upper()} | ingredients={result['ingredient_count']} | steps={result['instruction_count']} | {result['elapsed_seconds']}s")
        if result["error"]:
            print(f"  {result['error']}")
        if result["status"] != "success" and args.stop_on_error:
            break

    summary = output_dir / "batch_results.csv"
    write_summary(summary, results)
    successes = sum(r["status"] == "success" for r in results)
    print(f"\nCompleted {len(results)}: {successes} passed, {len(results)-successes} failed")
    print(f"Summary: {summary}")
    return 0 if successes == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
