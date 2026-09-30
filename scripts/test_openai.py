import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recipe_scraper.graph_pipeline import get_or_generate_graph  # noqa: E402
from recipe_scraper.llm import rewrite_instructions  # noqa: E402
from recipe_scraper.structured_ingredients import (  # noqa: E402
    ingredient_to_line,
    parse_ingredients,
)

PROMPT_PATH = Path("prompts/luna_recipe_rewrite.md")

# Change these paths if your benchmark uses different directories.
INPUT_DIR = Path("benchmarks/results/latest")
OUTPUT_DIR = Path("benchmarks/results/rewritten")


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def process_file(
    path: Path,
    prompt: str,
    output_dir: Path,
) -> None:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    instructions = data.get("recipe")

    if not isinstance(instructions, list) or not instructions:
        raise ValueError(f"{path}: missing or invalid 'recipe' field")

    ingredients = data.get("ingredients")
    if not isinstance(ingredients, list) or not all(isinstance(item, (str, dict)) for item in ingredients):
        raise ValueError(f"{path}: missing or invalid 'ingredients' field")
    lines = [item if isinstance(item, str) else ingredient_to_line(item) for item in ingredients]
    normalized_ingredients = parse_ingredients(lines)

    rewritten = rewrite_instructions(instructions, prompt)

    title = data.get("title")
    link = data.get("link")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"{path}: missing or invalid 'title' field")
    if not isinstance(link, str) or not link.strip():
        raise ValueError(f"{path}: missing or invalid 'link' field")

    output = {
        "title": title,
        "link": link,
        "ingredients": normalized_ingredients,
        "recipe": rewritten,
    }

    output_path = output_dir / path.name
    graph_path = output_dir.parent / "graphs" / path.name
    graph, warnings, cached = get_or_generate_graph(graph_path, output, lines)
    output_dir.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
    print(
        f"Graph {graph_path.name}: {len(graph.nodes)} nodes, {len(graph.edges)} edges, "
        f"{len(warnings)} warnings{' (cached)' if cached else ''}"
    )
    print(f"{path.name} -> {output_path}")


def files_from_summary(summary: Path, input_dir: Path) -> list[Path]:
    """Select only successful JSON files from the current extraction run."""
    with summary.open(encoding="utf-8-sig", newline="") as file:
        rows = csv.DictReader(file)
        files = [Path(row["json_file"]).resolve() for row in rows
                 if row.get("status") == "success" and row.get("json_file")]
    input_root = input_dir.resolve()
    for path in files:
        if path.parent != input_root:
            raise ValueError(f"Summary JSON is outside {input_root}: {path}")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize and rewrite extracted recipes.")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--summary", type=Path, help="Rewrite only successful rows in this batch CSV")
    args = parser.parse_args()
    try:
        prompt = load_prompt()
        files = (
            files_from_summary(args.summary, args.input_dir)
            if args.summary
            else sorted(args.input_dir.glob("*.json"))
        )
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Could not initialize post-processing: {exc}", file=sys.stderr)
        return 2

    if not files:
        print("No successful extracted recipes to rewrite.")
        return 1

    failures = 0
    for index, path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] Rewriting {path.name}")

        try:
            process_file(path, prompt, args.output_dir)
        except Exception as exc:
            failures += 1
            print(f"FAILED: {path.name}: {exc}")
    print(f"Rewrite completed: {len(files) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
