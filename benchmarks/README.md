# Benchmarks

Datasets live in `datasets/`; generated output belongs in `results/` and is ignored by Git.

```bash
python benchmarks/run.py
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

The torture set mixes live pages and deterministic local fixtures. Pytest only uses deterministic fixtures by default so ordinary test runs do not depend on the network.
