# Recipe Processing Pipeline

The pipeline converts a recipe URL into the canonical JSON described in [schema.md](schema.md). All extraction paths converge on one source-independent recipe representation.

```text
URL → fetch → extract → normalize/deduplicate → validate
    → normalize and parse ingredients → rewrite instructions
    → structured graph generation → graph validation → cache/render
```

## Fetch and extract

Fetch retrieves page HTML, follows redirects, applies configured timeouts and headers, and uses browser fetching where needed. It distinguishes network failures from extraction failures. Retries and timeouts must be explicit and bounded; never bypass anti-bot protections or extend limits silently to improve benchmark results.

Prefer usable Schema.org `Recipe` JSON-LD, including common arrays, `@graph`, nested objects, and multiple script blocks. If structured data is missing, malformed, or insufficient, use deterministic HTML extraction. Keep site-specific handling isolated and add regression coverage. Extract at least the title, source URL, ingredients, and instructions; keep diagnostics out of public recipe data.

## Normalize and validate

Normalize representation without changing meaning: flatten instruction structures, convert objects to text, remove empty entries, and clean whitespace and punctuation. Remove only clear duplicates (for example, after whitespace and case normalization). Similar entries with meaningful differences must remain: `1 cup flour` and `1 cup cake flour` are distinct.

Validate after extraction and deterministic cleanup. Require a non-empty title and source URL, at least one ingredient and instruction, and no empty or exact duplicate entries. Report failures with useful stage categories, such as `NO_RECIPE_FOUND`, `EXTRACTION_FAILED`, or `VALIDATION_FAILED`.

## Ingredient processing

Ingredient Parser handles sentence normalization, parsing, and post-processing. The pipeline removes shopping annotations that the parser may leave in names, then uses its batch API for ingredient lists. Its Pint-backed `convert_to` converts whole larger-unit equivalents (for example, teaspoons to tablespoons, grams to kilograms, and milliliters to liters). Fractions remain fractional; ranges, approximate amounts, and unrecognized units keep their original measurements. Do not infer missing quantities, ingredient density, or mass-to-volume conversions.

Serialization maps parsed results into `quantity`, `unit`, `ingredient`, and `preparation_type`, retaining preparation details and meaningful notes such as `to taste`, `divided`, and `for garnish`. It omits incidental comments and parser metadata. Post-processing scripts accept legacy saved JSON with string ingredients. `scripts/normalize_ingredients.py INPUT_DIR OUTPUT_DIR` normalizes saved results; `scripts/test_openai.py` applies the same ingredient stage when writing rewrites.

## Rewrite and final validation

The rewrite stage may use an LLM to make instructions concise and direct. Preserve ingredients, quantities, temperatures, durations, equipment, required actions, meaningful conditions, and order. Remove editorial filler and repetition; do not invent ingredients, measurements, times, temperatures, tools, techniques, substitutions, or safety claims.

The current rewrite script checks that output is a JSON array of strings. It does not yet compare cooking details against the source or fall back when they are lost. All OpenAI calls go through the LLM module, configured with `OPENAI_API_KEY` and optional `OPENAI_MODEL`.

## Output, diagnostics, and evaluation

Serialize only the four schema fields: `title`, `link`, `ingredients`, and `recipe`. Keep fetch method, extractor, failure stage, timings, duplicate counts, model, and token usage in internal diagnostics or benchmark output.

The comparison workflow passes each rewritten recipe to GPT-5.6 Luna for semantic graph generation, then validates and caches graph JSON separately from product JSON. See [graph.md](graph.md). The standalone extraction command produces the four-field recipe without rewriting or graph generation.

Use saved fixtures for unit, integration, and regression tests; normal tests must not call live websites or models. Evaluate changes with the relevant benchmark: fetch changes by fetch outcomes and latency, extraction changes by success and output structure, and rewrite changes by preservation, prose quality, token use, and cost. See [benchmarking.md](benchmarking.md).
