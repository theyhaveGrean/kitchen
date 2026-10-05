# Benchmarking

Benchmarks measure full-pipeline behavior on external recipe sources; deterministic tests protect known behavior. Ordinary `pytest` runs must not depend on websites, network conditions, anti-bot systems, or live model APIs. Live results can change without code changes.

## Suites

The standard dataset (about 100 normal recipe pages) estimates broad compatibility:

```bash
python benchmarks/run.py
python benchmarks/run.py --start 1 --limit 10
```

The torture suite probes difficult cases and is not a production success-rate estimate:

```bash
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

It combines live sources and local fixtures for cases such as malformed or duplicate JSON-LD, unusual nesting, partial data, JavaScript rendering, blocked requests, slow responses, and malformed fields. Datasets use CSV with at least `recipe_name,url`. Use local fixtures for deterministic edge cases and turn important live failures into regression tests when practical.

The comparison GUI is `python scripts/compare_results.py`. It extracts sources and runs compact semantic inference directly from canonical sidecars, followed by deterministic presentation. Saved source inputs can be processed without network fetching.

Offline extraction and semantic benchmarks:

```bash
python benchmarks/run.py benchmarks/datasets/torture_50.csv --fixtures-only
python benchmarks/semantic.py --output benchmarks/results/offline_semantic.json
```

Live semantic benchmarks use saved recipe data, not repeated webpage fetches:

```bash
python benchmarks/semantic.py --live --limit 10 --refresh --output benchmarks/results/live_semantic.json
python benchmarks/semantic.py --live --input-dir benchmarks/results/canonical --limit 5
```

The semantic runner records success, median/p90 latency, stage timings, model/reasoning, input/output tokens, repairs, cache state, ingredient coverage, and final validation grounding failures. Cached provenance tokens describe historical inference cost, not new API usage; distinguish cache hits before comparing token cost. Offline expected-semantic runs exercise validation/compiler/rendering without measuring model quality.

## Results and interpretation

Generated artifacts belong in ignored `benchmarks/results/`. Record enough to diagnose each case: recipe and URL/domain, success, failure stage, duration, ingredient and instruction counts, duplicate counts, and extractor. For model runs, also record model and available token usage; document pricing assumptions for estimated cost.

Compare candidates on the same dataset. Review fixed and regressed cases, failure stages, output counts, latency, cost, and—when rewriting—semantic preservation and prose quality. A successful API call is not necessarily a correct rewrite. Check ingredients, quantities, temperatures, times, equipment, conditions, actions, ordering, hallucinations, and concision.

Live latency and success are noisy because of site changes, outages, location, rate limits, and bot protection. Use repeated runs for latency conclusions. Do not hide failures, drop difficult cases for convenience, weaken validation, or silently extend timeouts or retries to improve scores. Keep benchmark artifacts out of source control unless intentionally preserving a result.

When a benchmark finds an important bug, reproduce it locally where practical, add a deterministic regression test, fix it, and rerun the relevant benchmark. Preserve the source instruction, baseline rewrite, and candidate rewrite when assessing prompt changes.

Semantic quality fixtures cover twenty patterns in `tests/fixtures/semantic_cases.json`: branches, pronouns, reserved liquid, divided ingredients, late components, optional garnish, multi-action steps, no-bake/one-pot flows, pan size, and prep actions. Graph live integration uses eleven patterns in `tests/fixtures/graph_cases.json`. Run `RUN_LIVE_GRAPH_TESTS=1 pytest tests/integration/test_graph_live.py` for real API/cache/compiler/SVG evaluation. Normal tests skip live calls.

## Refactor measurement (2026-10-04)

A single real-API before/after run used the same first five saved recipes. The old full-graph path had a median 18.375 seconds and 9,708 output tokens total. Compact semantic inference had a median 3.264 seconds and 1,362 output tokens total: about 82% lower median latency and 86% fewer output tokens in this small run. The old run used its default model reasoning; the new run explicitly used the primary low reasoning tier. These numbers are observations, not a broad production estimate or an isolated schema-only comparison.

The new ten-recipe live evaluation passed 10/10 with 100% ingredient coverage, median 3.026 seconds, p90 4.887 seconds, 3,419 output tokens including one repair, and a 10% repair rate. No final temperature/duration grounding failures remained after validation. This does not independently prove every inferred cooking dependency correct. Offline extraction passed 30/30 before and after; all twenty saved semantic cases passed after the refactor. Generated measurement artifacts are in ignored `benchmarks/results/refactor_baseline/` and `benchmarks/results/refactor/`.
