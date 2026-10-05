# Compiled Recipe Graphs

`RecipeGraph` is a deterministic presentation/API representation of a validated `SemanticRecipe`, not AI output. The old full-graph model prompt and generation function have been removed.

The compiler creates one ingredient node per canonical ingredient, one operation node per semantic material action, one intermediate (`op_001_out`) per consumed material output, and one final dish from the terminal operation. Ingredient IDs remain `ing_001` etc.; operation IDs remain sequential `op_001` etc. The final label is the canonical title. Source instruction text is recovered by step index. Prep actions use deterministic `prep_001` IDs and display separately without invented material links.

## Graph invariants

Nodes have `id`, `type`, `label`, nullable source ingredient fields, and nullable operation fields. Operation nodes require `action`; their label is the capitalized action alone. Ingredient/equipment/time/temperature descriptions never belong in the action label. Non-operation nodes have null cooking metadata and equipment `[]`.

Operation duration and temperature objects have all four fields: `min`, `nominal`, `max`, `unit`. Exact values repeat in all three numeric fields; ranges retain endpoints with null nominal; one-sided bounds retain only the stated bound; absent values are all null. Values are finite numeric values, ordered when present. Durations are nonnegative with second/minute/hour/day units; temperatures use F/C. Parameter phrases are copied by the model and parsed/converted by code. Qualitative timing such as overnight remains in semantic source metadata/source instructions when no safe numeric normalization exists.

Equipment and completion conditions remain in JSON but are not displayed in graph cells. Equipment is never a material intermediate. Internal target temperatures remain completion conditions rather than cooking heat.

Input edges connect ingredients/intermediates to operations. Output edges connect operations to their derived material products. Material references determine edges; the model cannot emit edges. The compiler never makes up dependencies to force convergence. Invalid topology fails before compilation. `validate_graph` remains an invariant checker for legacy graph consumers; semantic validation is authoritative for new generation.

## Layout and table presentation

The existing deterministic display/layout/SVG modules collapse intermediate products into operation links. Ingredients occupy rows, parallel streams pack independently, and merging actions span their material rows. The final title is a header instead of an extra dish cell. Cells show short actions with compact time/temperature/heat details. The grayscale chart uses no node-link arrows or empty bordered placeholders.

A separate material table comes directly from laminar semantic ingredient groups. It uses row spans for merges. Reused/reserved streams or overlapping nonlaminar groups use the general graph instead; this choice never changes cooking semantics.

## Cache and migration

Semantic caches are independently keyed by source content, schema, prompt content/versions, and both model tiers. Compiler or renderer changes reuse validated semantics with zero model calls. Graph JSON files are derived artifacts, accompanied by semantic sidecars for existing GUI/CLI workflows. Old graph-only caches are not authoritative and are regenerated from source semantics. Legacy four-field recipe JSON can still be imported, but ingredient originals reconstructed from parsed fields are marked as reconstructed; prefer preserved canonical sidecars.

```bash
python scripts/infer_semantic_recipe.py canonical.json -o conversion.json
python scripts/build_graph.py conversion.json -o graph.json --svg graph.svg --table recipe.html
python scripts/graph_recipe.py source-recipe.json --output graph-cache.json --svg graph.svg
```

When using the legacy graph command with `--source`, that source is authoritative; rewritten instructions are never used as the semantic input. Graph compilation and validation commands work completely offline with saved canonical/semantic artifacts.
