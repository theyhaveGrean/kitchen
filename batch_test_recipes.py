#!/usr/bin/env python3
"""
batch_test_recipes.py

Run recipe_extractor.py once for every URL in a CSV test set.

Expected CSV columns:
    id, site, recipe_name, category, url

Example:
    python batch_test_recipes.py
    python batch_test_recipes.py recipe_test_urls.csv
    python batch_test_recipes.py recipe_test_urls.csv --extractor recipe_extractor.py
    python batch_test_recipes.py recipe_test_urls.csv --output-dir extracted_recipes

Outputs:
    extracted_recipes/
        <id>.json
        batch_results.csv

The batch summary contains:
    status
    exit_code
    extraction_method
    confidence
    ingredient_count
    instruction_count
    title_extracted
    elapsed_seconds
    error

This intentionally invokes the extractor as a separate process for each recipe,
so each row tests the same CLI path a production worker/job could use.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {"id", "site", "recipe_name", "url"}


def safe_filename(value: str) -> str:
    """Turn an arbitrary recipe id/name into a filesystem-safe stem."""
    cleaned = "".join(
        ch if ch.isalnum() or ch in "-_." else "_"
        for ch in (value or "").strip()
    )
    cleaned = cleaned.strip("._")
    return cleaned or "recipe"


def load_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {', '.join(sorted(missing))}"
            )

        rows: list[dict[str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            normalized = {
                str(k): (v or "").strip()
                for k, v in row.items()
                if k is not None
            }

            if not normalized.get("url"):
                print(
                    f"Skipping CSV line {line_number}: empty URL",
                    file=sys.stderr,
                )
                continue

            if not normalized.get("id"):
                normalized["id"] = safe_filename(
                    normalized.get("recipe_name") or f"recipe_{line_number}"
                )

            rows.append(normalized)

    return rows


def parse_extractor_stdout(stdout: str) -> dict[str, Any]:
    """
    recipe_extractor.py writes the recipe JSON to stdout unless -o is used.
    Parse it and require the top level to be an object.
    """
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError("Extractor returned JSON, but the top level was not an object.")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_one(
    row: dict[str, str],
    *,
    extractor: Path,
    python_executable: str,
    output_dir: Path,
    timeout: int,
    render_js: bool,
    no_auto_render_js: bool,
) -> dict[str, Any]:
    recipe_id = safe_filename(row["id"])
    output_json = output_dir / f"{recipe_id}.json"

    cmd = [
        python_executable,
        str(extractor),
        row["url"],
        "--timeout",
        str(timeout),
    ]

    if render_js:
        cmd.append("--render-js")
    if no_auto_render_js:
        cmd.append("--no-auto-render-js")

    started = time.perf_counter()

    result: dict[str, Any] = {
        "id": row.get("id", ""),
        "site": row.get("site", ""),
        "recipe_name": row.get("recipe_name", ""),
        "category": row.get("category", ""),
        "url": row.get("url", ""),
        "status": "failed",
        "exit_code": "",
        "extraction_method": "",
        "confidence": "",
        "ingredient_count": "",
        "instruction_count": "",
        "title_extracted": "",
        "elapsed_seconds": "",
        "json_file": str(output_json),
        "error": "",
    }

    try:
        child_env = os.environ.copy()
        # Force UTF-8 inside the child interpreter as well as when decoding its
        # captured output. This prevents Windows code-page failures on Unicode
        # fractions, degree signs, curly quotes, etc.
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"

        proc = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout + 30,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )

        result["exit_code"] = proc.returncode
        result["elapsed_seconds"] = f"{time.perf_counter() - started:.3f}"

        if proc.returncode != 0:
            error = (proc.stderr or proc.stdout or "Unknown extractor error").strip()
            result["error"] = error[-4000:]
            return result

        try:
            payload = parse_extractor_stdout(proc.stdout)
        except Exception as exc:
            result["error"] = f"Could not parse extractor JSON: {exc}"
            raw_path = output_dir / f"{recipe_id}.stdout.txt"
            raw_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
            return result

        write_json(output_json, payload)

        ingredients = payload.get("ingredients") or []
        instructions = payload.get("instructions") or []

        result.update(
            {
                "status": "success",
                "extraction_method": payload.get("extraction_method", ""),
                "confidence": payload.get("confidence", ""),
                "ingredient_count": len(ingredients)
                if isinstance(ingredients, list)
                else "",
                "instruction_count": len(instructions)
                if isinstance(instructions, list)
                else "",
                "title_extracted": payload.get("title", "") or "",
                "error": "",
            }
        )

        warnings = payload.get("warnings")
        if warnings:
            if isinstance(warnings, list):
                result["error"] = "Warnings: " + " | ".join(map(str, warnings))
            else:
                result["error"] = f"Warnings: {warnings}"

        return result

    except subprocess.TimeoutExpired:
        result["elapsed_seconds"] = f"{time.perf_counter() - started:.3f}"
        result["error"] = f"Timed out after {timeout + 30} seconds"
        return result
    except Exception as exc:
        result["elapsed_seconds"] = f"{time.perf_counter() - started:.3f}"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result


def write_summary(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "site",
        "recipe_name",
        "category",
        "url",
        "status",
        "exit_code",
        "extraction_method",
        "confidence",
        "ingredient_count",
        "instruction_count",
        "title_extracted",
        "elapsed_seconds",
        "json_file",
        "error",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def main() -> int:
    here = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Batch-test recipe_extractor.py against URLs from a CSV."
    )
    parser.add_argument(
        "csv_file",
        nargs="?",
        default=str(here / "recipe_test_urls.csv"),
        help="CSV containing recipe URLs (default: recipe_test_urls.csv beside this script)",
    )
    parser.add_argument(
        "--extractor",
        default=str(here / "recipe_extractor.py"),
        help="Path to recipe_extractor.py",
    )
    parser.add_argument(
        "--output-dir",
        default=str(here / "extracted_recipes"),
        help="Directory for per-recipe JSON and batch_results.csv",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Extractor HTTP timeout in seconds (default: 20)",
    )
    parser.add_argument(
        "--render-js",
        action="store_true",
        help="Force the extractor's Playwright rendering path",
    )
    parser.add_argument(
        "--no-auto-render-js",
        action="store_true",
        help="Disable the extractor's automatic Playwright fallback",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for child extractor processes",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately after the first failed extraction",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_file).expanduser().resolve()
    extractor = Path(args.extractor).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 2
    if not extractor.exists():
        print(f"Extractor not found: {extractor}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        rows = load_rows(csv_path)
    except Exception as exc:
        print(f"Could not read test CSV: {exc}", file=sys.stderr)
        return 2

    if not rows:
        print("No recipe rows found in CSV.", file=sys.stderr)
        return 2

    print(f"Testing {len(rows)} recipes")
    print(f"Extractor: {extractor}")
    print(f"Output:    {output_dir}")
    print()

    results: list[dict[str, Any]] = []

    for index, row in enumerate(rows, start=1):
        label = row.get("recipe_name") or row.get("id") or row["url"]
        print(f"[{index}/{len(rows)}] {row.get('site', '')}: {label}")

        result = run_one(
            row,
            extractor=extractor,
            python_executable=args.python,
            output_dir=output_dir,
            timeout=args.timeout,
            render_js=args.render_js,
            no_auto_render_js=args.no_auto_render_js,
        )
        results.append(result)

        if result["status"] == "success":
            print(
                "  OK"
                f" | method={result['extraction_method']}"
                f" | confidence={result['confidence']}"
                f" | ingredients={result['ingredient_count']}"
                f" | steps={result['instruction_count']}"
                f" | {result['elapsed_seconds']}s"
            )
            if result["error"]:
                print(f"  {result['error']}")
        else:
            print(f"  FAILED | {result['elapsed_seconds']}s")
            print(f"  {result['error']}")
            if args.stop_on_error:
                break

        print()

    summary_path = output_dir / "batch_results.csv"
    write_summary(summary_path, results)

    successes = sum(r["status"] == "success" for r in results)
    failures = len(results) - successes

    print("=" * 72)
    print(f"Completed: {len(results)}")
    print(f"Successes: {successes}")
    print(f"Failures:  {failures}")
    print(f"Summary:   {summary_path}")

    # Non-zero exit makes this suitable for CI/regression testing.
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
