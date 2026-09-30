# Architecture

Recipe Scraper is a staged Python package. The pipeline coordinates fetching, extraction, normalization, validation, ingredient processing, instruction rewriting, and serialization. Each stage communicates through source-independent recipe models. For runtime behavior, see [pipeline.md](pipeline.md).

## Modules and boundaries

The package is organized around these responsibilities:

| Area | Responsibility |
| --- | --- |
| `fetch/` | Retrieve HTML with configured timeouts and report network failures. |
| `extractor.py` and `parsers/` | Select usable Schema.org Recipe data or deterministic DOM extraction. |
| `models.py` | Define the internal recipe model. |
| `normalize.py` and `structured_ingredients.py` | Deduplicate, parse ingredients, and produce product JSON. |
| `validation.py` | Reject likely roundup pages. |
| `llm.py` | Centralize OpenAI client, model configuration, rewriting, and structured graph calls. |
| `graph.py` / `graph_pipeline.py` | Define and validate graph data; generate and cache it. |
| `graph_display.py` | Collapse semantic product nodes into display operation links. |
| `graph_layout.py` | Convert display graphs into deterministic TRN process geometry. |
| `graph_render.py` | Draw the TRN layout as SVG without API calls. |

The CLI calls the public pipeline API and handles input/output and exit behavior. Scripts are for development workflows; reusable logic belongs in `src/recipe_scraper/`.

Dependencies flow from the CLI to the pipeline and from the pipeline to stage modules. Lower-level modules must not import the CLI or pipeline. Fetching does not interpret recipes; extraction does not depend on OpenAI; the LLM layer does not fetch pages; serialization does not extract data.

The comparison workflow is coordinated by `scripts/compare_results.py` and `scripts/test_openai.py`; `llm.py` owns OpenAI calls. Graph validation, storage, and rendering remain independent of that workflow.

## Data flow

```text
extractor CLI → fetch → extraction → normalization / ingredient parsing → recipe JSON
comparison GUI → benchmark extraction → rewrite script → LLM module → rewritten JSON
                                                 → graph validator/cache → graph renderer
```

Keep transformations explicit and independently testable. Deterministic parsing, validation, deduplication, arithmetic, and unit conversion stay in code. OpenAI SDK calls go through `llm.py`, using `OPENAI_API_KEY`, optional `OPENAI_MODEL` for rewriting, and optional `OPENAI_GRAPH_MODEL` for graph generation.

Extractors may retain raw ingredient lines internally. Product serialization parses cleaned lines into `quantity`, `unit`, `ingredient`, and `preparation_type`; post-processing scripts also support saved legacy JSON with string ingredients. Keep diagnostics—such as extractor, failure stage, timings, and token usage—separate from product data.

## Errors and tests

Preserve the stage and useful category of failures, such as `FETCH_TIMEOUT`, `FETCH_BLOCKED`, `NO_RECIPE_FOUND`, `VALIDATION_FAILED`, or `LLM_FAILED`. Avoid collapsing structured failures into generic errors.

Tests should follow module boundaries: unit tests cover components, integration tests use saved fixtures, and regression tests preserve observed fixes. Live websites and model calls belong in explicit benchmarks or evaluations, not the deterministic test suite. Keep public APIs small and avoid exposing implementation details accidentally.
