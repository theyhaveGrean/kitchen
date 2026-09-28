#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

here = Path(__file__).resolve().parent
cmd = [
    sys.executable,
    str(here / "batch_test_recipes.py"),
    str(here / "recipe_test_urls_100.csv"),
    "--extractor",
    str(here / "recipe_extractor.py"),
    "--output-dir",
    str(here / "extracted_recipes_100"),
]
raise SystemExit(subprocess.call(cmd))
