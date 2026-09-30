"""Parse and normalize saved recipe ingredients with Ingredient Parser.

Run: python scripts/normalize_ingredients.py INPUT_DIR OUTPUT_DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from recipe_scraper.structured_ingredients import (  # noqa: E402
    ingredient_to_line,
    parse_ingredients,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    if args.input_dir.resolve() == args.output_dir.resolve():
        parser.error("Input and output directories must differ")
    files = sorted(args.input_dir.glob("*.json"))
    if not files:
        parser.error(f"No JSON files found in {args.input_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        ingredients = data.get("ingredients")
        if not isinstance(ingredients, list) or not all(isinstance(item, (str, dict)) for item in ingredients):
            raise ValueError(f"{path}: invalid ingredients")
        lines = [item if isinstance(item, str) else ingredient_to_line(item) for item in ingredients]
        data["ingredients"] = parse_ingredients(lines)
        target = args.output_dir / path.name
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name} -> {target}")


if __name__ == "__main__":
    main()
