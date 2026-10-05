# Benchmarks and comparison GUI

Datasets live in `datasets/`; generated results, stage caches, and provenance stay in ignored `results/`. See [benchmarking](../docs/benchmarking.md) for metrics and interpretation.

```bash
python benchmarks/run.py
python benchmarks/run.py benchmarks/datasets/torture_50.csv --fixtures-only --output-dir benchmarks/results/fixtures
python benchmarks/semantic.py
python benchmarks/semantic.py --live --limit 10 --refresh
python benchmarks/semantic.py --live --input-dir benchmarks/results/canonical --limit 5
```

The extraction runner saves four-field product JSON and separate original-preserving canonical sidecars. Semantic benchmarks use saved canonical/product inputs and never re-fetch pages. Offline runs validate twenty expected semantic fixtures; live runs call configured primary/repair tiers and record timings, tokens, coverage, grounding failures, repairs, and cache state.

Run `python scripts/compare_results.py` for the PyQt GUI. **Run full pipeline** extracts selected rows, then infers source semantics and compiles graphs/presentation. **Post-process saved results** skips fetching and prefers canonical sidecars. Files in the historical `rewritten` directory now contain downstream source-preserving presentation; no mandatory prose rewrite occurs. `scripts/test_openai.py` is a deprecated command alias for `postprocess_saved.py`.

The normal views show source and presentation, a grayscale graph, and a material table when topology permits. Stage JSON/provenance is available under **Show stage details**. Graph generation works from source without requiring any presentation result, and failed semantics leave the source view usable.
