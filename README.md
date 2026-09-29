# Recipe Scraper

Recipe Scraper is a Python package for taking recipe pages from the internet and converting them into a consistent, concise prose recipe JSON format.

It owns the full processing pipeline:

```text
recipe URL
    ↓
fetch page
    ↓
extract recipe data
    ↓
normalize structure
    ↓
de-duplicate
    ↓
validate
    ↓
normalize ingredients / units
    ↓
rewrite instructions into concise prose
    ↓
validate final output
    ↓
recipe JSON
```

The goal is to accept recipes from many different websites and produce one predictable representation that downstream applications can consume without needing to understand the source site's structure.

## Output

The final product format is intentionally small:

```json
{
  "title": "Recipe title",
  "link": "https://example.com/recipe",
  "ingredients": [
    {"quantity": "1", "unit": "cup", "ingredient": "flour", "preparation_type": null},
    {"quantity": "2", "unit": null, "ingredient": "eggs", "preparation_type": null}
  ],
  "recipe": [
    "Preheat oven to 350°F.",
    "Mix flour and eggs.",
    "Bake until golden."
  ]
}
```

The final instructions are normalized into concise cooking prose while preserving the information needed to prepare the recipe.

## Design Goals

The package prioritizes:

- consistent output across recipe websites
- deterministic processing where practical
- preservation of cooking-critical information
- concise, readable recipe instructions
- conservative de-duplication
- clear separation between pipeline stages
- reproducible testing
- measurable live-web performance

Deterministic code is preferred for parsing, validation, de-duplication, arithmetic, and unit handling.

LLMs may be used where language understanding or rewriting materially improves the final recipe representation.

## Repository Layout

```text
src/recipe_scraper/     recipe-processing package
tests/                  deterministic pytest coverage
benchmarks/             live and torture benchmarks
scripts/                developer entry points
docs/                   architecture, decisions, and plans
.github/workflows/      CI
```

## Install

For local development:

```bash
python -m pip install -r requirements.txt
scrapling install
```

The base package does not require browser dependencies so deterministic tests can run without live web access.
Ingredient parsing uses `ingredient_parser_nlp` and its NLTK English tagger data.
Install the tagger once before running offline:

```bash
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"
```

LLM-backed pipeline stages require an OpenAI API key:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

Keep `.env` out of version control.

## Process a Recipe

After installation:

```bash
recipe-scraper "https://example.com/recipe"
```

Write the result to a file:

```bash
recipe-scraper "https://example.com/recipe" -o recipe.json
```

From a checkout:

```bash
python scripts/extract_recipe.py "https://example.com/recipe"
```

The command runs the complete recipe pipeline and returns the final product JSON.

## Pipeline

### Fetch

Retrieve the recipe page and handle network behavior such as redirects, timeouts, and browser-backed fetching where required.

### Extract

Prefer structured Schema.org / JSON-LD recipe data when usable.

Fall back to deterministic HTML extraction when structured data is missing or insufficient.

### Normalize

Convert source-specific data into the package's internal recipe representation.

This stage is responsible for making downstream processing independent of the source website.

### De-duplicate

Remove repeated ingredients or instructions caused by duplicated source data or extraction behavior.

De-duplication should remain conservative so legitimate recipe information is not discarded.

### Validate

Reject malformed intermediate recipes rather than allowing corrupted data to continue through the pipeline.

### Ingredient and Unit Normalization

Normalize ingredient representations and units where deterministic processing can do so safely.

Arithmetic and normal unit conversion should not rely on an LLM.

### Prose Rewriting

Rewrite extracted recipe instructions into concise, kitchen-friendly prose.

For example:

```text
Before:
Preheat the oven to 325°F. Lightly spray an 8x8 baking dish—not a
9x9 dish—with cooking spray. Line it with parchment paper and spray
the parchment.

After:
Preheat oven to 325°F. Spray an 8x8 baking dish with cooking spray.
Line with parchment and spray again.
```

Rewriting should remove irrelevant editorial prose without changing cooking-critical information such as:

- ingredients
- quantities
- temperatures
- cooking times
- required equipment
- required actions
- step order

### Final Validation

Validate the rewritten recipe before serialization.

If a transformation produces unusable output, the pipeline should fail clearly or fall back to a safe earlier representation rather than silently returning corrupted instructions.

## Tests

Run the deterministic test suite with:

```bash
pytest
```

Individual groups:

```bash
pytest tests/unit
pytest tests/integration
```

Normal tests do not require live recipe websites.

Important real-world failures should be converted into deterministic regression cases whenever practical.

Before committing:

```bash
pytest
ruff check .
mypy .
```

## Benchmarks

Tests protect known behavior. Benchmarks measure the complete pipeline against real recipes.

Run the standard live benchmark:

```bash
python benchmarks/run.py
```

Run the torture suite:

```bash
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

The torture benchmark includes difficult sources and local fixtures intended to expose edge cases rather than represent normal production performance.

Benchmark output is written under:

```text
benchmarks/results/
```

and is not committed.

Useful benchmark metrics include:

- extraction success
- failure stage
- processing time
- ingredient count
- instruction count
- duplicates detected
- extractor used
- model usage
- token usage
- estimated LLM cost

## Architecture

The pipeline is intentionally staged:

```text
fetch
  ↓
extract
  ↓
normalize
  ↓
deduplicate
  ↓
validate
  ↓
ingredient normalization
  ↓
prose rewrite
  ↓
final validation
  ↓
serialize
```

Each stage should have a clear responsibility and should not quietly absorb unrelated behavior.

This makes the package easier to test, benchmark, and modify without destabilizing the rest of the pipeline.

## Documentation

This README provides the project overview and basic development workflow.

Detailed documentation belongs under:

```text
docs/
├── architecture/
├── decisions/
└── plans/
```

Use `docs/architecture/` for how the current system works, `docs/decisions/` for important architectural decisions, and `docs/plans/` for substantial implementation work.

The repository should contain enough context for a new developer or coding agent to understand and modify the system without relying on previous chat history.
