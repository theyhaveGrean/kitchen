# Benchmarking

This document describes how Recipe Scraper evaluates real-world pipeline performance.

Benchmarks complement deterministic tests. They do not replace them.

## Purpose

The project uses benchmarks to answer questions such as:

- How many real recipe pages can the pipeline process successfully?
- Which pipeline stage fails most often?
- Which websites or structures expose weaknesses?
- Did an extractor change improve or reduce live success?
- Did a rewrite prompt improve prose without losing recipe information?
- How much latency and model cost does the complete pipeline introduce?

Benchmarks should make changes measurable rather than relying on anecdotal testing.

## Tests vs Benchmarks

Deterministic tests answer:

> Does known behavior still work?

Live benchmarks answer:

> How does the current implementation behave against real external sources?

These are intentionally different.

Normal `pytest` runs should not depend on:

- external websites
- network conditions
- anti-bot systems
- live model APIs

Live benchmark results may change even when the code does not.

## Benchmark Sets

The repository currently has two major benchmark categories.

### Standard Benchmark

The standard benchmark contains approximately 100 normal recipe pages.

Run with:

```bash
python benchmarks/run.py
```

To process a slice of the dataset, use 1-based `--start` and `--limit`:

```bash
python benchmarks/run.py --start 1 --limit 10
```

The GUI in `scripts/compare_results.py` exposes these as **Start at** and
**Count**, and passes only successful extracted recipes from that slice to
ingredient normalization and rewriting.

Its purpose is to approximate broad real-world compatibility.

The dataset should contain a diverse selection of:

- recipe publishers
- site architectures
- structured-data formats
- recipe styles
- ingredient counts
- instruction formats

It should not intentionally overrepresent pathological cases.

### Torture Benchmark

The torture suite contains difficult cases designed to expose weaknesses.

Run with:

```bash
python benchmarks/run.py benchmarks/datasets/torture_50.csv --output-dir benchmarks/results/torture
```

The current suite combines:

- live difficult sources
- deterministic local fixtures

Example failure modes represented by the torture suite may include:

- malformed JSON-LD
- multiple Recipe objects
- duplicated recipe data
- unusual instruction nesting
- partial structured data
- JavaScript-rendered pages
- anti-bot behavior
- slow responses
- unusual Unicode
- empty or malformed fields

The torture benchmark is not intended to estimate normal production success rate.

A lower success rate here may be acceptable if the suite contains intentionally pathological inputs.

## Dataset Format

Benchmark datasets should use a consistent CSV format.

At minimum:

```text
recipe_name,url
```

Example:

```csv
recipe_name,url
Chocolate Chip Cookies,https://example.com/cookies
Brownies,https://example.com/brownies
```

If the benchmark runner requires additional fields, those fields should be documented and shared across benchmark datasets where practical.

Avoid creating multiple incompatible CSV formats without a strong reason.

## Local Fixtures

Local fixtures are used when a failure can be represented deterministically.

They are especially useful for:

- malformed JSON-LD
- duplicated structures
- unusual HTML
- extraction edge cases
- previously observed regressions

A local fixture allows the behavior to be tested without relying on the original website remaining unchanged.

Important live failures should be converted into local regression coverage when practical.

## Benchmark Output

Generated benchmark results belong under:

```text
benchmarks/results/
```

Generated output should normally be ignored by Git.

Benchmark results are artifacts, not source code.

## Core Metrics

Each benchmark case should capture enough information to understand success or failure.

Useful fields include:

```text
recipe_name
url
domain
success
failure_stage
duration_seconds
ingredient_count
instruction_count
duplicate_ingredients
duplicate_instructions
extractor_used
```

Additional metrics may be added where useful.

## Failure Stages

Failures should identify the stage that failed.

Examples:

```text
FETCH_TIMEOUT
FETCH_BLOCKED
HTTP_ERROR
NO_RECIPE_FOUND
EXTRACTION_FAILED
VALIDATION_FAILED
LLM_FAILED
```

Do not classify every failure simply as:

```text
failed
```

Stage-level reporting makes benchmark changes actionable.

## Timing

Measure end-to-end duration when possible.

Additional per-stage timing may be useful for:

```text
fetch
extract
normalize
rewrite
total
```

Timing results should be interpreted carefully because live network performance is variable.

Use repeated runs when making latency-sensitive conclusions.

## LLM Metrics

When a benchmark exercises LLM-backed processing, record available usage information such as:

```text
model
input_tokens
cached_input_tokens
output_tokens
```

Where pricing information is available, estimated cost may also be calculated.

Cost calculations should clearly state the model pricing assumptions used.

## Rewrite Evaluation

A successful API call does not automatically mean a successful rewrite.

Rewrite benchmarks should evaluate whether the model:

- preserved ingredients
- preserved quantities
- preserved temperatures
- preserved cooking times
- preserved required equipment
- preserved meaningful conditions
- avoided hallucination
- removed unnecessary prose
- produced consistent concise instructions

A prompt change should not be judged only on subjective readability.

Information preservation matters more than making prose shorter.

## Comparing Changes

When evaluating a code or prompt change, compare runs using the same benchmark set.

Useful comparisons include:

```text
baseline
vs.
candidate
```

Consider:

- overall success rate
- cases fixed
- cases regressed
- failure-stage distribution
- latency
- model token usage
- cost
- rewrite quality

Avoid claiming improvement based solely on aggregate success if important cases regressed.

## Extraction Changes

When extraction logic changes, inspect:

- success/failure changes
- ingredient counts
- instruction counts
- duplicate counts
- extractor selected
- validation failures

Unexpected jumps in ingredient or instruction counts may indicate extraction errors even when the case technically succeeds.

## Fetch Changes

When fetch behavior changes, inspect:

- request success
- timeout frequency
- blocked responses
- browser fallback usage
- latency

Do not silently increase timeout limits simply to improve benchmark scores.

That trades benchmark appearance for worse product behavior.

## Prompt Changes

Prompt changes should be treated similarly to code changes.

Use a fixed evaluation set where possible.

Compare:

```text
original source instruction
baseline rewrite
candidate rewrite
```

Review both:

- semantic preservation
- prose quality

Prompt versions should be identifiable so benchmark results remain reproducible.

## Regression Policy

If a benchmark exposes an important bug:

1. understand the failure,
2. reproduce it locally where practical,
3. add a deterministic regression test,
4. fix the implementation,
5. confirm the regression test passes,
6. rerun the relevant benchmark.

Do not depend forever on a live page to protect a known behavior.

## Live-Web Limitations

Benchmark results are affected by factors outside the repository.

Examples include:

- website redesigns
- server outages
- geolocation
- rate limits
- bot protection
- changed JSON-LD
- temporary latency
- JavaScript requirements

For this reason:

```text
live benchmark failure ≠ automatically a code regression
```

Likewise:

```text
passing pytest ≠ guaranteed live compatibility
```

Both forms of testing are required for different reasons.

## Benchmark Integrity

Benchmarks should measure product behavior honestly.

Do not:

- hide failures
- silently skip difficult cases
- increase timeouts only to raise the success rate
- remove cases because they became inconvenient
- count malformed output as success
- weaken validation to improve benchmark statistics

If a benchmark case is no longer useful, document why before replacing or removing it.

## Adding a Benchmark Case

When adding a case:

1. choose a descriptive `recipe_name`,
2. add the source URL or fixture,
3. confirm the benchmark runner accepts the row,
4. run the case,
5. verify its result is meaningful.

Add cases because they improve coverage, not merely to increase dataset size.

## Interpreting Results

The standard benchmark should be used primarily for broad compatibility.

The torture benchmark should be used primarily for robustness and edge-case discovery.

A useful benchmark summary may include:

```text
Total cases:             100
Successful:               94
Failed:                    6

Fetch failures:            2
Extraction failures:       3
Validation failures:       1

Median duration:         2.1 s
```

For candidate changes, also report:

```text
Fixed cases:       4
Regressed cases:   1
Net change:       +3
```

This is more informative than reporting only a new percentage.

## Benchmarking Principles

1. Keep deterministic tests and live benchmarks separate.
2. Use the same datasets when comparing implementations.
3. Track failure stages, not only success rate.
4. Convert important failures into deterministic regression tests.
5. Measure LLM cost and semantic preservation when models are involved.
6. Do not optimize benchmark scores by weakening correctness requirements.
7. Treat live-web measurements as noisy.
8. Preserve difficult cases because they reveal weaknesses.
9. Keep benchmark output out of source control unless deliberately preserving a result.
10. Prefer actionable metrics over large quantities of unused data.
