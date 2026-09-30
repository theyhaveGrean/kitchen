# Benchmarks

Datasets live in `datasets/`; generated results go in Git-ignored `results/`.

```bash
python benchmarks/run.py
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

The torture dataset combines difficult live pages and deterministic local fixtures. Ordinary pytest runs use saved fixtures and do not require network access. See [../docs/benchmarking.md](../docs/benchmarking.md) for dataset guidance and result interpretation.

## Comparison GUI

Run:

```bash
python scripts/compare_results.py
```

**Run full pipeline** fetches and extracts the selected dataset rows into `benchmarks/results/latest`. **Start at** is 1-based; **Count** selects a number of rows or **All** through the end. Successful recipes are ingredient-normalized and rewritten into `benchmarks/results/rewritten`. The GUI displays extraction and rewritten output and updates its recipe list as results arrive.

Both stages use ingredient objects with `quantity`, `unit`, `ingredient`, and `preparation_type`. Rewriting requires `OPENAI_API_KEY` and uses `OPENAI_MODEL` when set.

**Post-process saved results** skips fetching and processes each `*.json` in `benchmarks/results/latest`, continuing past invalid files and reporting them in the log. It writes to `benchmarks/results/rewritten` and has the same API-key and model requirements.

Both actions now also generate validated semantic graphs in `benchmarks/results/graphs`. The GUI's **Graph** tab renders a cached graph and shows its edges and warnings. Graph generation defaults to `gpt-5.6-luna`; set `OPENAI_GRAPH_MODEL` to change it. See [../docs/graph.md](../docs/graph.md).
