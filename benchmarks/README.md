# Benchmarks

Datasets live in `datasets/`; generated output belongs in `results/` and is ignored by Git.

```bash
python benchmarks/run.py
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

The torture set mixes live pages and deterministic local fixtures. Pytest only uses deterministic fixtures by default so ordinary test runs do not depend on the network.

The comparison GUI can run extraction, ingredient normalization, and LLM rewriting
with per-recipe progress:

```bash
python scripts/compare_results.py
```

Click **Run full pipeline** to fetch and extract the selected dataset rows. Extraction writes to `benchmarks/results/latest`.
Set **Start at** to `1` and **Count** to `10` to process the first ten dataset rows;
set **Count** to **All** to run from the chosen start row through the end.
Successful recipes from that run are cleaned and parsed with Ingredient Parser,
then rewritten into `benchmarks/results/rewritten`.
Both extraction and rewritten JSON use `quantity`, `unit`, `ingredient`, and
`preparation_type` inside each ingredient. The GUI shows both stages'
output and refreshes the recipe list as results arrive. The rewrite stage requires
`OPENAI_API_KEY` and uses `OPENAI_MODEL` if set.

To process files already saved in `benchmarks/results/latest` without fetching,
click **Post-process saved results**. This runs ingredient normalization and
instruction rewriting for every `*.json` file in that directory and writes
results to `benchmarks/results/rewritten`. Invalid files are reported individually
in the log while other files continue processing. This action also requires
`OPENAI_API_KEY` and uses `OPENAI_MODEL` if set.
