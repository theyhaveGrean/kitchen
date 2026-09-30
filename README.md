# Recipe Scraper

Recipe Scraper turns recipe URLs into consistent JSON for downstream kitchen applications. It prefers deterministic extraction and normalization, using an LLM only for instruction rewriting. See [pipeline](docs/pipeline.md), [schema](docs/schema.md), [architecture](docs/architecture.md), and [benchmarking](docs/benchmarking.md) for details.

The comparison workflow can also use GPT-5.6 Luna to turn a rewritten recipe into a validated, cached cooking graph. The app renders that graph from JSON; see [recipe graphs](docs/graph.md).

## Output

```json
{
  "title": "Recipe title",
  "link": "https://example.com/recipe",
  "ingredients": [
    {"quantity": "1", "unit": "cup", "ingredient": "flour", "preparation_type": null}
  ],
  "recipe": ["Preheat oven to 350°F.", "Mix flour and bake until golden."]
}
```

## Install and configure

```bash
python -m pip install -r requirements.txt
scrapling install
```

Ingredient parsing uses `ingredient_parser_nlp` and NLTK tagger data. For offline use, download the tagger once:

```bash
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"
```

LLM rewriting requires `OPENAI_API_KEY`; `OPENAI_MODEL` optionally selects the model. Keep `.env` out of version control.

## Run

```bash
recipe-scraper "https://example.com/recipe"
recipe-scraper "https://example.com/recipe" -o recipe.json
```

From a checkout, use `python scripts/extract_recipe.py URL`.

## Development

Run deterministic tests with `pytest`; they do not require live recipe websites. Before committing, run:

```bash
pytest
ruff check .
mypy .
```

The standard live benchmark is `python benchmarks/run.py`. Run the torture set with:

```bash
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

Benchmark output goes under `benchmarks/results/` and is not committed. See [benchmarks/README.md](benchmarks/README.md) for the comparison GUI and saved-result workflow.
