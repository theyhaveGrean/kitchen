# Architecture

The LLM produces a minimal `SemanticRecipe`. Application code validates it and deterministically compiles it into `RecipeGraph` and presentation formats. Source recipes are authoritative; prose rewriting never precedes or controls semantic inference.

```text
URL -> static fetch/extract -> CanonicalRecipe -> extraction cache
                                  |
                         compact semantic inference
                                  |
                         deterministic validation
                                  |
                   one repair only when invalid
                                  |
                         semantic cache + provenance
                                  |
              +-------------------+------------------+
              |                   |                  |
        graph compiler       source prose       material table
              |
       existing TRN layout/SVG
```

## Modules and dependency direction

| Module | Responsibility |
| --- | --- |
| `fetch/web.py` | Static HTTP and optional Scrapling browser fetch; no recipe interpretation or AI. |
| `extractor.py`, `parsers/` | JSON-LD-first extraction, structured metadata and DOM fallbacks. Parser-family import surfaces re-export extraction helpers. |
| `models.py` | Internal extraction transport model. |
| `canonical.py` | Preserve source lines, stable ingredient IDs, one-based source steps; advisory ingredient parsing and legacy product imports. |
| `structured_ingredients.py`, `ingredient_cleanup.py` | Deterministic ingredient parsing/normalization; source originals are retained independently. |
| `semantic.py` | Compact AI response schema and version constants. |
| `llm.py` | Only OpenAI SDK boundary; configurable primary/repair tiers and optional downstream prose rewriting. |
| `semantic_validation.py`, `semantic_topology.py` | Source-grounded structured issues, referential integrity, terminal/DAG/laminar analysis. |
| `semantic_pipeline.py` | Independent semantic caching, bounded validation-based repair, controlled failure and provenance. |
| `graph_compile.py` | Zero-API ingredient/operation/intermediate/final node and edge construction. |
| `graph.py`, `graph_measurements.py` | Compiled graph models/invariants and deterministic measurement parsing/normalization. |
| `graph_pipeline.py` | Compatibility facade for existing graph consumers; calls semantic inference and the compiler, never direct graph inference. |
| `graph_display.py`, `graph_layout.py`, `graph_render.py` | Deterministic TRN geometry and grayscale SVG. |
| `presentation.py`, `prose_pipeline.py` | Conservative source prose, optional separately cached AI prose with fidelity fallback, compact laminar material tables. |
| `cache.py` | SHA-256 stage keys, conservative URL normalization, same-host page canonical URLs, atomic writes. |
| `conversion.py` | Extraction/semantic/presentation stage coordination and timings. |
| `stage_cli.py` | Stage-specific commands; graph and validation work offline. |

Models and deterministic utilities do not call pipelines or UI. `conversion.py` coordinates stages. Rendering never depends on API access. Canonical data is not mutated by inference; generated labels, source text, and ingredients are looked up by the compiler. Details of [schemas](schema.md), [runtime behavior](pipeline.md), [graph rendering](graph.md), and [benchmarking](benchmarking.md) live in their respective documents.

The comparison GUI remains PyQt6; there is no Streamlit application. It displays source and downstream presentation, a compiled graph, and a material table. Stage details are opt-in. `scripts/postprocess_saved.py` replaces mandatory rewrite-first processing; `scripts/test_openai.py` is only a command alias.
