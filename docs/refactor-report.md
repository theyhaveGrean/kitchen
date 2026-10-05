# Recipe pipeline refactor report

Implemented and verified on 2026-10-04. The attached refactor brief informed the architectural changes; the requested cooking-action and structured graph metadata rules are enforced in the compiled graph.

## Architecture and behavior

The old path extracted and parsed ingredients, rewrote instructions with an LLM, and asked another model to produce complete graph nodes, copied source fields, labels, products, and edges. The new path is:

```text
static-first extraction → CanonicalRecipe → compact SemanticRecipe inference
    → source/topology validation → deterministic graph/prose/table compilation
```

Prose rewriting is optional and downstream. Extraction, inference, validation, graph compilation, and conversion have independent CLI entry points. The existing PyQt comparison UI consumes canonical/semantic artifacts directly, includes table presentation where supported, and hides detailed provenance/validation diagnostics behind a control.

`CanonicalRecipe` preserves original ingredient lines and source instructions with stable ingredient IDs; ingredient parsing is advisory. `SemanticRecipe` contains cooking actions, material references, source parameter phrases, prep actions, and unresolved references. The model does not generate graph plumbing. See [schema](schema.md) and [architecture](architecture.md).

Compiled operations have an explicit action, an action-only label, structured `{min, nominal, max, unit}` duration and temperature objects, equipment arrays, and optional completion conditions. Missing numeric information remains null. Numeric parsing and unit equivalence are deterministic. Equipment is preserved internally and excluded from visible graph/table cells. Equipment, bare timing/temperature values, and descriptive states cannot become material output nodes. Source prose retains qualitative conditions and other cooking-critical clauses.

Validation reports structured issues for invalid IDs/steps/references, forward dependencies/cycles, empty inputs, duplicate operations, unused ingredients, unsupported products, fabricated portions/equipment/conditions, and unsupported numeric parameters. Optional supplies and explicit unresolved references remain visible warnings. No artificial merge is added to satisfy the single-terminal requirement. See [graph rules](graph.md).

Extraction caching uses normalized URL, extractor version, and a configurable TTL. Semantic caching hashes meaningful source content, strict schema, prompt contents/versions, and both model tiers; source diagnostics and advisory parser output do not invalidate it. Optional AI prose has a separate cache. Graphs are derived artifacts that can be rebuilt after compiler changes without another model call. Cache records are atomic, malformed records are misses, and cached semantics are revalidated.

The normal inference path makes one primary call. Invalid schema or semantics permit one structured repair using the configured stronger reasoning/model tier. There are at most two semantic attempts; SDK automatic retries are disabled. Transport failures do not trigger semantic repair. Failed repair exposes source data and structured failure rather than fabricating a graph. Available model/reasoning, token usage, repair counts, timestamps, versions, cache state, and stage timings are recorded. See [pipeline](pipeline.md) and [decisions](decisions.md).

## File changes

Created reusable modules under `src/recipe_scraper/`:

- `canonical.py`, `cache.py`, `semantic.py`, `semantic_topology.py`, `semantic_validation.py`
- `semantic_pipeline.py`, `graph_compile.py`, `graph_measurements.py`
- `presentation.py`, `prose_pipeline.py`, `conversion.py`, `stage_cli.py`

Created entry points and evaluation resources:

- `scripts/infer_semantic_recipe.py`, `scripts/validate_semantic_recipe.py`, `scripts/build_graph.py`, `scripts/convert_recipe.py`, `scripts/postprocess_saved.py`, `scripts/__init__.py`
- `prompts/semantic_recipe.md`, `prompts/semantic_repair.md`, `benchmarks/semantic.py`
- `tests/fixtures/semantic_cases.json`
- Unit tests for canonical/cache behavior, semantic validation/topology/compilation, bounded inference/repair, static extraction, and optional prose fallback
- Integration tests for offline stage CLI behavior and the actual PyQt graph/table UI
- `docs/decisions.md` and this report

Substantially modified extraction/fetch/model metadata, the centralized LLM module, the graph schema/display/cache facade, package exports, benchmark orchestration, comparison UI, graph CLI, and existing graph/live tests. Updated README, AGENTS, benchmark README, and architecture/pipeline/schema/graph/benchmark documentation. Corrected existing typing errors exposed by the required whole-project Mypy check.

Removed `prompts/luna_recipe_graph.md` and direct full-graph model generation. Deprecated `scripts/test_openai.py` as a compatibility alias to source-based post-processing. Retained the rewrite prompt solely for optional downstream prose.

## Verification and measurements

| Check | Result |
| --- | --- |
| Full offline pytest | 186 passed; 11 live tests skipped by default |
| Explicit real-API graph integration | 11 passed |
| Ruff | Passed |
| Mypy | Passed, 66 source files |
| Offline extraction benchmark | 30/30 before and after |
| Saved semantic quality benchmark | 20/20 |
| Fresh real-API semantic benchmark | 10/10, 100% ingredient coverage, one repair |
| UI | Actual offscreen PyQt graph/table rendered from saved source and semantics without prose or API calls; preview inspected |

Regression coverage includes source preservation despite parser failure, URL/canonical identity, corrupt/expired caches, independent cache invalidation, compiler changes without new inference, strict AI output, bounded repair and transport failures, source fallback, branching/divided/reserved materials, important equipment/pan dimensions, structured numeric ranges/exact values, hidden equipment, and offline commands/UI. Pytest reports 17 third-party lxml deprecation warnings.

The same first five saved recipes had a one-run median latency of 18.375 seconds on the old full-graph path versus 3.264 seconds on compact semantics, and 9,708 versus 1,362 output tokens. That is approximately 82% lower median latency and 86% fewer output tokens for this sample. The new ten-case run had median 3.026 seconds, p90 4.887 seconds, and 3,419 output tokens including repair. The old path used its default reasoning configuration; the new path used explicit low reasoning. These are small one-run observations, not production guarantees or an isolated schema-only comparison. See [benchmark methodology and results](benchmarking.md). Generated evidence remains under ignored `benchmarks/results/refactor_baseline/` and `benchmarks/results/refactor/`.

## Limits and compatibility

Validation cannot independently prove every inferred cooking relationship; explicit unresolved references remain warnings. Recipes with genuinely independent terminal dishes fail graph conversion rather than receive an invented join. Reserved/reused outputs and nonlaminar grouping remain graph-renderable but may not have a table representation. Unquantified phrases such as “overnight” remain in source/semantic data without invented numeric duration.

Legacy four-field recipe JSON remains accepted and emitted for compatibility. Previously discarded original ingredient wording cannot be reconstructed exactly; legacy imports record this limitation. Old graph-only caches are obsolete: a valid semantic artifact is required for deterministic recompilation. Operation metadata and stable internal IDs changed, so external consumers of old graph JSON must migrate. Static-first extraction changes diagnostic method names while retaining legacy parser-method information. The historical `rewritten` result directory now contains downstream presentation rather than a mandatory inference input.
