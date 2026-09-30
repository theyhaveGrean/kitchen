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

The comparison GUI is `python scripts/compare_results.py`. It can run extraction and pass successful rows to ingredient normalization and rewriting. See [../benchmarks/README.md](../benchmarks/README.md) for its run controls and saved-result workflow.

## Results and interpretation

Generated artifacts belong in ignored `benchmarks/results/`. Record enough to diagnose each case: recipe and URL/domain, success, failure stage, duration, ingredient and instruction counts, duplicate counts, and extractor. For model runs, also record model and available token usage; document pricing assumptions for estimated cost.

Compare candidates on the same dataset. Review fixed and regressed cases, failure stages, output counts, latency, cost, and—when rewriting—semantic preservation and prose quality. A successful API call is not necessarily a correct rewrite. Check ingredients, quantities, temperatures, times, equipment, conditions, actions, ordering, hallucinations, and concision.

Live latency and success are noisy because of site changes, outages, location, rate limits, and bot protection. Use repeated runs for latency conclusions. Do not hide failures, drop difficult cases for convenience, weaken validation, or silently extend timeouts or retries to improve scores. Keep benchmark artifacts out of source control unless intentionally preserving a result.

When a benchmark finds an important bug, reproduce it locally where practical, add a deterministic regression test, fix it, and rerun the relevant benchmark. Preserve the source instruction, baseline rewrite, and candidate rewrite when assessing prompt changes.

Graph evaluation uses ten representative recipe patterns in `tests/fixtures/graph_cases.json`. Set `RUN_LIVE_GRAPH_TESTS=1` and run `pytest tests/integration/test_graph_live.py` to exercise the real GPT-5.6 Luna API, graph validation, and SVG rendering. Review semantic branches and unresolved references in addition to passing assertions. The ordinary suite skips these live calls.
