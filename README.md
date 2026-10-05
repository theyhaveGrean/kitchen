# Recipe Scraper

A source-preserving recipe pipeline for kitchen displays. Static JSON-LD extraction and ingredient parsing are deterministic. One compact model call normally infers cooking semantics; code validates it and compiles graphs, source prose, and grayscale material tables.

```text
URL -> CanonicalRecipe -> SemanticRecipe -> graph / prose / table
       extraction cache    inference cache    deterministic rendering
```

See [pipeline](docs/pipeline.md), [schemas](docs/schema.md), [architecture](docs/architecture.md), [graphs](docs/graph.md), [decisions](docs/decisions.md), and [benchmarking](docs/benchmarking.md).

## Setup

```bash
python -m pip install -r requirements.txt
scrapling install
python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"
```

Static extraction does not need a browser. Scrapling is used only for enabled browser fallback. `OPENAI_API_KEY` is required for semantic inference. `OPENAI_SEMANTIC_MODEL` and `OPENAI_SEMANTIC_REASONING` configure the primary tier; `OPENAI_REPAIR_MODEL` and `OPENAI_REPAIR_REASONING` configure the bounded repair tier. Legacy `OPENAI_GRAPH_MODEL` remains a primary-model fallback. Keep `.env` gitignored.

## Commands

The original four-field product output remains available:

```bash
recipe-scraper "https://example.com/recipe" -o recipe.json
python scripts/extract_recipe.py URL --canonical -o canonical.json
```

Independent stages support saved sources without repeatedly scraping:

```bash
recipe-pipeline extract URL -o canonical.json
python scripts/infer_semantic_recipe.py canonical.json -o conversion.json
python scripts/validate_semantic_recipe.py conversion.json
python scripts/build_graph.py conversion.json -o graph.json --svg graph.svg --table recipe.html
python scripts/convert_recipe.py URL -o conversion.json --svg graph.svg
python scripts/postprocess_saved.py --input-dir benchmarks/results/latest --output-dir benchmarks/results/rewritten
```

Use `--html-file` with `recipe-pipeline extract` or the conversion script for local HTML. `--refresh-extraction` and `--refresh-semantic` bypass their respective caches independently. Optional `--llm-prose` rewriting occurs only after valid semantics and falls back to source if it loses details. Default prose and graph/table rendering require no second model call.

The PyQt comparison GUI is `python scripts/compare_results.py`. Its source, presentation, graph, and material-table views share the canonical/semantic pipeline. Stage diagnostics are hidden until requested.

## Verification

```bash
pytest
ruff check .
mypy .
python benchmarks/run.py benchmarks/datasets/torture_50.csv --fixtures-only
python benchmarks/semantic.py
python benchmarks/semantic.py --live --limit 10 --refresh
```

Ordinary tests and offline semantic benchmarks use saved fixtures. Live APIs require explicit test/benchmark selection. Results and caches stay in ignored `benchmarks/results/`.
