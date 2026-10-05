# Architectural decisions

## Minimal semantics as AI output

**Decision:** the model emits `SemanticRecipe`, while source extraction emits deterministic `CanonicalRecipe`. Application code validates semantics and compiles `RecipeGraph`, source prose, and table/TRN presentation.

Direct graph generation duplicated source ingredient fields, source instructions, operations, product nodes, labels, final nodes, and edges. It expanded output tokens, exposed source data to mutation, and made graph plumbing another probabilistic inference task. Mandatory prose rewriting added a second model call and removed source information before dependency inference.

The compact representation reserves inference for material inputs, reference resolution, action splitting, branches/merges, material names, and source-phrase attribution. IDs, labels, material outputs, edges, source lookups, numeric parsing, and layout are deterministic. This reduces latency/output and makes validation, caching, repair, model substitution, and renderer testing independent.

**Consequences:** graph-only caches are obsolete; legacy product imports remain supported but cannot recover already-discarded raw source text. Multiple independent dishes fail explicitly rather than receive artificial merge operations. Prose is conservative by default; optional rewriting happens only downstream and falls back to source on loss. Semantic validation protects source evidence but cannot prove every cooking dependency semantically correct. Tests and live evaluations remain necessary.

## Independent stage caches and bounded escalation

Extraction is cached separately from inference, so prompt changes do not re-scrape pages. Semantic keys cover both configured tiers, source content, schema, and prompt contents/versions; diagnostics do not invalidate them. Graph compilation is cheap and always reproducible. Optional AI prose has its own cache.

The normal path uses one primary inference call. Invalid schema/semantics allow one repair with structured issues and a stronger configured reasoning/model tier. Transport failures do not cause semantic regeneration. Failed repairs expose structured failure and canonical source; no graph is fabricated.
