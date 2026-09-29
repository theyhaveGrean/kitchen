# Architecture

This document describes the software architecture of Recipe Scraper.

For the end-to-end recipe transformation flow, see `pipeline.md`.

## Overview

Recipe Scraper is a staged Python pipeline that converts recipe pages from the internet into a consistent prose recipe JSON format.

The architecture separates:

- fetching
- extraction
- normalization
- validation
- ingredient processing
- prose rewriting
- serialization
- benchmarking

Each stage should have a narrow responsibility and communicate through stable internal representations.

## Package Layout

The package should remain organized approximately as:

```text
src/recipe_scraper/
├── __init__.py
├── cli.py
├── pipeline.py
│
├── fetch/
│   ├── __init__.py
│   └── fetcher.py
│
├── extraction/
│   ├── __init__.py
│   ├── extractor.py
│   ├── jsonld.py
│   └── html.py
│
├── normalization/
│   ├── __init__.py
│   ├── recipe.py
│   ├── ingredients.py
│   └── units.py
│
├── validation/
│   ├── __init__.py
│   └── recipe.py
│
├── llm/
│   ├── __init__.py
│   ├── client.py
│   ├── prompts.py
│   └── rewrite.py
│
├── models/
│   ├── __init__.py
│   └── recipe.py
│
└── serialization/
    ├── __init__.py
    └── recipe.py
```

The exact file structure may evolve, but the boundaries between responsibilities should remain clear.

## Dependency Direction

High-level orchestration should depend on lower-level components, not the reverse.

```text
CLI
 ↓
pipeline
 ↓
┌─────────────┬──────────────┬─────────────┐
fetch       extraction    normalization
                             ↓
                         validation
                             ↓
                           LLM
                             ↓
                       serialization
```

Lower-level modules should not import the pipeline or CLI.

For example:

- `fetch` should not know about recipe rewriting.
- `extraction` should not know about OpenAI.
- `llm` should not fetch web pages.
- `serialization` should not contain extraction logic.

## Pipeline Orchestration

`pipeline.py` owns the ordering of stages.

It should coordinate components rather than implement their internal logic.

Conceptually:

```python
page = fetch(url)
recipe = extract(page, url)
recipe = normalize(recipe)
recipe = deduplicate(recipe)
validate(recipe)

recipe = normalize_ingredients(recipe)
recipe = rewrite_recipe(recipe)
validate_final(recipe)

return serialize(recipe)
```

The actual implementation may differ, but pipeline orchestration should remain explicit and easy to follow.

Avoid hiding major processing stages inside deeply nested helper calls.

## Fetch Layer

The fetch layer is responsible only for retrieving source content.

Responsibilities include:

- HTTP retrieval
- redirect handling
- timeouts
- request headers
- optional browser-backed fetching
- returning source HTML
- reporting fetch failures

The fetch layer should not:

- parse recipe ingredients
- rewrite instructions
- perform recipe validation
- know about the final JSON schema

Scrapling and similar browser/network dependencies belong here.

## Extraction Layer

The extraction layer converts source HTML into an initial recipe representation.

Primary strategies:

1. Schema.org Recipe JSON-LD
2. deterministic HTML fallback
3. explicit extraction failure

Structured extraction should be preferred when reliable.

Extractor implementations should converge on the same internal recipe model.

Source-specific logic should be isolated rather than spread throughout generic parsers.

## Models

Internal recipe models define the contract between pipeline stages.

They should:

- be source-independent
- contain enough information for downstream processing
- remain easy to serialize
- support deterministic validation
- avoid carrying arbitrary website-specific state

The internal model may contain more information than final product JSON, but source diagnostics should remain clearly separated from product data.

## Normalization

Normalization converts extracted values into consistent internal representations.

Examples include:

- whitespace normalization
- instruction flattening
- punctuation normalization
- ingredient text cleanup
- unit normalization
- de-duplication

`structured_ingredients.py` is the boundary from cleaned ingredient lines to the
four ingredient fields in product JSON. Extractors retain source ingredient strings;
the serializer invokes the parser. Post-processing scripts reconstruct lines from
saved ingredient objects before applying Ingredient Parser's quantity and unit
processing.

Normalization should not alter recipe meaning.

Operations that can change semantic content belong in later, explicit transformation stages.

## Validation

Validation defines boundaries between pipeline stages.

At minimum, validation should exist:

1. after extraction and deterministic normalization
2. after AI-assisted transformation

The purpose is to prevent invalid data from silently propagating.

Validation should return or raise structured failures that identify what went wrong.

## LLM Layer

All model interaction should be isolated under `llm/`.

Other modules should not import the OpenAI SDK directly.

The LLM layer owns:

- client initialization
- model configuration
- prompts
- request construction
- response parsing
- usage metadata
- model-specific error handling

Higher-level code should depend on functions representing product behavior, for example:

```python
rewrite_recipe(recipe)
```

rather than raw OpenAI API calls.

This makes model changes easier and allows deterministic tests to mock the model boundary.

## Prompt Ownership

Prompts are application logic and should be version-controlled.

Prompts should live in one predictable location such as:

```text
src/recipe_scraper/llm/prompts.py
```

Avoid embedding slightly different copies of prompts across scripts or modules.

Major prompt changes should be benchmarked.

## Serialization

Serialization is the final boundary between internal data and product JSON.

It should:

- produce the canonical schema
- omit internal diagnostics
- guarantee predictable field types
- preserve field ordering where useful for readability

Serialization should not perform major transformations.

If substantial cleanup is required at serialization time, that logic belongs earlier in the pipeline.

## Diagnostics

Diagnostics should be separate from final recipe output.

Internal diagnostics may contain:

- fetch method
- extractor used
- failure stage
- processing durations
- duplicate counts
- model name
- token usage
- estimated model cost

Benchmarks may request diagnostics explicitly.

Normal product serialization should not expose them.

## CLI

The CLI is a thin interface over the package.

It should:

1. parse arguments,
2. call the public pipeline API,
3. write or print the result,
4. map known failures to useful exit behavior.

Business logic should not live primarily in CLI code.

The same pipeline should be usable programmatically.

## Scripts

`scripts/` contains development conveniences, not core implementation.

Scripts may:

- invoke benchmarks
- test external services
- inspect extraction behavior
- run one-off developer workflows

Reusable logic should be moved into `src/recipe_scraper/`.

## Tests

Tests mirror architectural boundaries.

```text
tests/
├── unit/
├── integration/
├── regression/
└── fixtures/
```

Unit tests exercise individual modules.

Integration tests exercise multiple deterministic stages together.

Regression tests preserve fixes for previously observed failures.

Live website and live LLM evaluations belong in benchmark or explicit evaluation workflows rather than ordinary deterministic tests.

## Configuration

Runtime configuration should come from explicit configuration or environment variables.

Examples:

```text
OPENAI_API_KEY
OPENAI_MODEL
```

Secrets must never be committed.

Avoid modules that read large amounts of global environment state during import.

Prefer configuration that can be overridden cleanly in tests.

## Public API

The package should expose a small public interface.

Conceptually:

```python
from recipe_scraper import process_recipe

recipe = process_recipe("https://example.com/recipe")
```

Internal parser and implementation details should not become public APIs accidentally.

This allows internals to evolve without breaking consumers.

## Error Handling

Errors should preserve the pipeline stage that failed.

Useful categories include:

```text
FETCH_TIMEOUT
FETCH_BLOCKED
HTTP_ERROR
NO_RECIPE_FOUND
EXTRACTION_FAILED
VALIDATION_FAILED
LLM_FAILED
```

Do not collapse every failure into a generic exception if structured information is available.

Benchmark tooling depends on distinguishing failure modes.

## Architectural Principles

The architecture should continue to follow these rules:

1. Keep pipeline stages explicit.
2. Keep network behavior separate from recipe interpretation.
3. Keep deterministic transformations separate from LLM transformations.
4. Keep product data separate from diagnostics.
5. Keep OpenAI-specific code behind one interface.
6. Keep the canonical schema stable.
7. Prefer small modules with clear responsibilities.
8. Avoid duplicate implementations of the same behavior.
9. Make important boundaries independently testable.
10. Optimize for clarity before abstraction.
