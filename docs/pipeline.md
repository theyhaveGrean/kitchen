# Recipe Processing Pipeline

```text
URL -> extraction cache lookup -> static HTTP -> JSON-LD Recipe
                                    |
                         other metadata / HTML fallback
                                    |
                     browser only if static content fails
                                    |
                         CanonicalRecipe -> cache
                                    |
                       one compact semantic model call
                                    |
                     validation -> optional one repair
                                    |
                         valid SemanticRecipe -> cache
                                    |
                   graph compile / prose / material table
```

## Extraction and source fidelity

`extract_canonical` caches by normalized URL, extractor version, and canonical schema version. Tracking parameters and fragments do not create extra entries; recipe query values remain distinct. Same-host page canonical URLs are stored and cached as aliases. Extraction records expire after 24 hours by default (`RECIPE_EXTRACTION_CACHE_TTL`), and explicit refresh bypasses them. Prompt/model changes never invalidate extraction.

Static HTTP is first. Complete JSON-LD recipes return without running fallback parsers or a browser. Broken/unavailable JSON-LD can use microdata/RDFa, itemprops, Scrapling DOM parsing, and HTML heuristics. Browser fallback only runs when static extraction is incomplete and is enabled. The default network budget remains 60 seconds; the browser receives the remaining budget. Explicit `--render-js` forces a browser; `--no-auto-render-js` disables fallback. HTTP access denials and human-verification pages are failures, not reasons to bypass protections. Cloudflare challenge solving is disabled.

Diagnostics distinguish `jsonld_static`, `jsonld_browser`, `html_static`, and `html_browser`, retain the parser family, and record browser usage/timings. Saved HTML fixtures need no network.

Canonicalization preserves original ingredient text and source instructions, apart from deterministic text cleanup and conservative duplicate removal. Ingredient Parser is advisory: a parsing failure retains the original line and null parsed fields. Quantities, units, preparation notes, divided/reserved uses, optional serving ingredients, and source equipment are never replaced by model output.

## Semantic inference and repair

Inference reads compact original ingredient lines with `ing_001` IDs and numbered source instructions. It does not read rewritten prose or whole webpage HTML. The model returns material actions, references to canonical ingredients/earlier operations, optional material output names, source parameter phrases, equipment, completion criteria, portion wording, and separate non-material prep actions. It does not emit graph nodes, edges, labels, coordinates, ingredient copies, or source-instruction copies.

Deterministic validation returns structured issues. Success normally uses one call. Schema or semantic failure allows one correction using the source, prior parsed semantics if available, structured issues, and the repair tier. Valid structure should remain intact. There are at most two inference attempts; transport failures do not trigger a semantic repair, and SDK transport retries are disabled. Failed validation never creates a semantic cache or graph.

The defaults are `gpt-5.6-luna` with `low` reasoning, then the same model with `medium` reasoning for repair. Configuration is explicit:

| Environment variable | Meaning |
| --- | --- |
| `OPENAI_API_KEY` | Server-side API secret; never logged or committed. |
| `OPENAI_SEMANTIC_MODEL` | Primary inference model; legacy `OPENAI_GRAPH_MODEL` is a fallback. |
| `OPENAI_SEMANTIC_REASONING` | Primary reasoning effort. |
| `OPENAI_REPAIR_MODEL` | Repair model, defaulting to the primary model. |
| `OPENAI_REPAIR_REASONING` | Repair reasoning effort. |
| `OPENAI_MODEL` | Optional downstream prose model only. |
| `RECIPE_CACHE_DIR` | Independent stage cache root (default `benchmarks/results/cache`). |
| `RECIPE_EXTRACTION_CACHE_TTL` | Extraction TTL in seconds. |

## Compilation and presentation

The compiler copies canonical ingredients, derives action labels, recovers exact instructions via step indices, parses numeric parameters, generates material outputs and final dish, and derives all material edges. Prep/environment actions become separate header bars without guessed dependency edges. Prep supplies remain in canonical ingredient rows; they are accounted for in semantic validation but do not create equipment products.

The default prose presentation conservatively formats source steps without a model call. This deliberately retains clauses absent from a compact graph. `--llm-prose` optionally runs downstream rewriting with an independent cache and conservative fidelity checks; invalid or lossy output falls back to the source. Graph presentation does not depend on rewriting.

Laminar, merge-oriented flows can use a material table with ingredient rows and merged action cells. Reserved/split/nonlaminar flows retain the general TRN graph; no forced merges or artificial cooking actions are introduced to fit a table.

## Failure and diagnostics

`SemanticInferenceFailure` includes attempt count, structured issues, and the last parsed output. The conversion CLI emits the canonical recipe and source presentation on failure; saved post-processing writes a failure sidecar and retains the source presentation. The UI can always show available source data. Multiple terminal material streams currently fail explicitly; separate independent dishes should be ingested separately rather than fabricated into one final graph.

Stage timings include fetch, extraction, browser fallback, ingredient parsing, inference, validation, repair, graph compilation, prose presentation, and total time. Provenance includes model, reasoning, prompt/schema versions, creation time, validation status, repairs, canonical source hash, and available token usage. Expensive historical usage is retained in cache provenance; cache-hit timings are current lookup/validation timings.

For development commands see [README](../README.md); for evaluation see [benchmarking](benchmarking.md).
