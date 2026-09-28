# Recipe Scraper

A recipe extraction package with deterministic pytest coverage and separate live/regression benchmarks.

## Repository layout

```text
src/recipe_scraper/     importable package
tests/                  pytest unit + deterministic integration tests
benchmarks/             live/torture datasets and benchmark runner
scripts/                developer convenience entry points
.github/workflows/       CI
```

## Install

For local extraction and development:

```bash
python -m pip install -e ".[fetch,dev]"
scrapling install
```

The base package deliberately does not require Scrapling so fixture/unit tests can run without browser dependencies.

## Extract a recipe

After installation:

```bash
recipe-scraper "https://example.com/recipe"
recipe-scraper "https://example.com/recipe" -o recipe.json
```

From a checkout without installing the console script:

```bash
python scripts/extract_recipe.py "https://example.com/recipe"
```

Product JSON remains intentionally small:

```json
{
  "title": "Recipe title",
  "link": "https://example.com/recipe",
  "ingredients": ["1 cup flour", "2 eggs"],
  "recipe": ["Mix the ingredients.", "Bake until done."]
}
```

Ingredients and steps are de-duplicated before serialization. Extraction diagnostics are available only through the private benchmark debug flag.

## Tests

```bash
pytest
pytest tests/unit
pytest tests/integration
```

All 30 local torture fixtures are represented as deterministic pytest integration cases. Normal test runs do not require live websites.

## Benchmarks

100 live recipe pages:

```bash
python benchmarks/run.py
```

50-case torture suite (20 live + 30 local fixtures):

```bash
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

Generated benchmark output is ignored under `benchmarks/results/`.
