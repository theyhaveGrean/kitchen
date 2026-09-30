# Recipe graphs

The comparison pipeline generates a semantic cooking graph after instruction rewriting:

```text
structured rewritten recipe → GPT-5.6 Luna → RecipeGraph JSON → validation → cache → SVG/UI
```

Luna receives only the compact recipe fields and, when available, original ingredient lines from the extraction result. It determines ingredient flow, operations, intermediates, dependencies, and references. Application code validates and renders the result. The graph lives in `benchmarks/results/graphs/NAME.json`; product recipe JSON retains the four fields in [schema.md](schema.md).

## Schema

`RecipeGraph` has `nodes`, `edges`, `unresolved_references`, and `warnings`. Node types are `ingredient`, `operation`, `intermediate`, and `final`. Every node has an ID, type, label, and nullable fields for source ingredient ID, amount, unit, preparation, original text, instruction index and text, temperature, duration, and heat level. Edge types are `input` (ingredient or intermediate to operation), `output` (operation to intermediate or final), and `dependency` (operation to operation). An ingredient may feed multiple operations when divided or reused. Operations can run in parallel and combine later.

The validator rejects duplicate IDs, invalid references or edge direction, cycles, unknown or altered source ingredients, missing producers for products, invalid step indices or source instruction text, and a final product unreachable from any ingredient. It reports missing or unused ingredients, components disconnected from the final product, and unresolved references as warnings. On validation failure, the app gives Luna the errors and its prior graph for one correction attempt. It does not invent edges to repair uncertain semantics.

The graph cache key covers the structured recipe, original ingredient lines, model, prompt, and schema. Viewing a current graph only reads the cache. Changing any of those inputs triggers regeneration. `OPENAI_GRAPH_MODEL` selects the graph model; the default is `gpt-5.6-luna`. `OPENAI_API_KEY` is loaded server-side from the environment or `.env`.

The renderer converts the cached semantic graph through a `TRNDisplayGraph` into TRN geometry without another model call. The display graph collapses intermediate products into operation links; intermediate nodes remain in the cached `RecipeGraph`. Ingredients occupy rows on the left and extend to their first use; unmapped ingredients stay as short marked cells. Each operation is packed against its preceding operation on the same material path. Nearby boundaries on parallel branches align by widening the preceding operation, while distant branches retain independent positions. A completed branch extends to its merge when that space is free. Row heights follow wrapped ingredient text, and operation widths fit their labels and metadata. The final dish name appears as the chart title instead of a trailing cell. Global actions such as preheating appear in separate header bars. The SVG uses a grayscale palette and system sans serif font, with no node-link arrows or empty bordered placeholders.

## Use

The comparison GUI's **Run full pipeline** and **Post-process saved results** actions generate graphs after rewriting. Its **Graph** tab displays the app-rendered SVG, edge list, warnings, and a **Generate graph** button for a selected rewritten recipe.

To generate or inspect one saved recipe without rewriting:

```bash
python scripts/graph_recipe.py benchmarks/results/rewritten/mb_pancakes.json --source benchmarks/results/latest/mb_pancakes.json --svg benchmarks/results/graphs/mb_pancakes.svg
```

The CLI prints a debug edge list and writes the validated graph cache and optional SVG. A real API evaluation covering ten recipe patterns is in `tests/integration/test_graph_live.py`; run it with `RUN_LIVE_GRAPH_TESTS=1 pytest tests/integration/test_graph_live.py` when network and API access are available. Ordinary tests skip those calls.
