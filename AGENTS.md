# AGENTS.md

## Project

Recipe extraction and normalization pipeline for the kitchen display.

Prefer deterministic code over LLMs whenever practical.

## Architecture

- Reusable code belongs in `src/`.
- Tests belong in `tests/`.
- Scripts belong in `scripts/`.
- Benchmarks belong in `benchmarks/`.
- Project documentation belongs in `docs/`.

Relevant docs:

- `docs/pipeline.md` — end-to-end recipe processing flow
- `docs/architecture.md` — package structure, module boundaries, and dependency direction
- `docs/schema.md` — canonical recipe JSON schema and invariants
- `docs/benchmarking.md` — benchmark design, datasets, metrics, and interpretation

Read only the documentation relevant to the task.

## Core Rules

- Prefer Schema.org Recipe JSON-LD for extraction.
- Keep extraction separate from LLM rewriting.
- Do not use an LLM for deterministic parsing, arithmetic, or unit conversion.
- All extractors must produce the canonical recipe schema defined in `docs/schema.md`.
- Do not return duplicate ingredients or instructions.
- Deduplication must be conservative.
- Do not silently increase network timeouts or add unlimited retries.
- Do not bypass CAPTCHAs or anti-bot protections.
- Preserve cooking-critical information during rewriting:
  - ingredients
  - quantities
  - temperatures
  - times
  - required actions
- If LLM output is invalid or loses important information, use the original text.

For pipeline behavior, follow `docs/pipeline.md`.

For architectural boundaries and module responsibilities, follow `docs/architecture.md`.

## OpenAI

All OpenAI calls should go through the repository's LLM module.

Configuration comes from environment variables:

```text id="4ccgdo"
OPENAI_API_KEY
OPENAI_MODEL
```

Never commit or log secrets.

`.env` must remain gitignored.

## Tests

Use `pytest`.

For bug fixes, add a regression test when practical.

Normal tests should use saved fixtures rather than depend on live recipe websites.

When extraction or pipeline behavior changes, run the relevant benchmark described in `docs/benchmarking.md`.

Do not weaken valid tests merely to make a change pass.

## Documentation

Update documentation when architecture, schema, pipeline behavior, or externally meaningful behavior changes.

Update the relevant document rather than duplicating the same information across multiple files:

- pipeline changes → `docs/pipeline.md`
- architecture changes → `docs/architecture.md`
- product schema changes → `docs/schema.md`
- benchmark changes → `docs/benchmarking.md`

Keep documentation focused on the current system.

## Scope

Make the smallest clean change that solves the requested problem.

Avoid unrelated refactoring.

Remove obsolete duplicate code when its replacement has been validated.

## Before Committing

Run all of the following from the repository root:

```bash id="0jj43t"
pytest
ruff check .
mypy .
```

Do not commit if any of these fail.

If a check cannot be run, state that clearly instead of treating the change as verified.