# Recipe Processing Pipeline

This document describes the end-to-end pipeline used by Recipe Scraper to convert recipe pages from the internet into a consistent prose recipe JSON format.

The pipeline owns the full transformation from source URL to final product output.

```text
recipe URL
    ↓
fetch page
    ↓
extract recipe data
    ↓
normalize structure
    ↓
de-duplicate
    ↓
validate intermediate recipe
    ↓
normalize ingredients and units
    ↓
parse ingredient fields
    ↓
rewrite instructions into concise prose
    ↓
validate transformed recipe
    ↓
serialize final recipe JSON
```

The main design goal is to make recipes from different websites converge on one predictable output format while preserving all cooking-critical information.

---

## 1. Input

The pipeline begins with a recipe URL.

Example:

```text
https://example.com/chocolate-chip-cookies
```

The source site may expose recipe information through:

- Schema.org JSON-LD
- embedded structured metadata
- conventional HTML
- JavaScript-rendered content
- multiple duplicated representations of the same recipe

The rest of the pipeline should not depend on how the source site represents the recipe.

---

## 2. Fetch

The fetch stage retrieves the source page.

Responsibilities include:

- following redirects
- enforcing configured timeouts
- supplying an appropriate user agent
- returning source HTML
- using browser-backed fetching where required
- distinguishing network failures from parsing failures

Fetching should not contain recipe-specific interpretation logic.

Typical failure categories include:

```text
FETCH_TIMEOUT
FETCH_BLOCKED
HTTP_ERROR
FETCH_FAILED
```

Retries and timeouts should remain explicit and bounded.

The pipeline should not silently increase timeouts or retry indefinitely to improve benchmark success rates.

---

## 3. Structured Extraction

The extractor first looks for structured recipe data.

Schema.org `Recipe` JSON-LD is the preferred source when usable.

The parser should support common structures including:

- a single Recipe object
- arrays of objects
- `@graph`
- nested Recipe objects
- pages containing multiple JSON-LD blocks

The extractor should recover at least:

- title
- source URL
- ingredients
- instructions

Additional source metadata may be retained internally if required for later processing, but it should not automatically become part of the public recipe schema.

---

## 4. HTML Fallback Extraction

If structured data is unavailable, malformed, or insufficient, the pipeline may fall back to deterministic HTML extraction.

HTML fallback exists to increase source compatibility, but should remain isolated from structured-data parsing.

The fallback extractor may use:

- semantic HTML structure
- common recipe markup
- visible ingredient lists
- instruction containers
- known structural patterns

Avoid unnecessary source-specific logic in shared parsing code.

If site-specific handling is required, isolate it and add regression coverage.

---

## 5. Internal Recipe Representation

All extraction paths converge on one internal recipe representation before later processing.

The internal representation should be source-independent.

Conceptually:

```json
{
  "title": "Chocolate Chip Cookies",
  "link": "https://example.com/cookies",
  "ingredients": [
    "2 cups all-purpose flour",
    "2 eggs"
  ],
  "recipe": [
    "Preheat the oven to 350°F.",
    "Mix the ingredients.",
    "Bake for 12 minutes."
  ]
}
```

The exact internal model may contain additional fields required for diagnostics or transformations, but downstream stages should not depend on source-specific structures.

---

## 6. Structural Normalization

The normalization stage converts extractor output into a consistent internal shape.

Typical responsibilities include:

- flattening nested instruction structures
- converting instruction objects into text
- stripping empty entries
- normalizing whitespace
- standardizing basic text representation
- ensuring ingredients and instructions are represented consistently

This stage should normalize representation without changing the meaning of the recipe.

---

## 7. De-duplication

Some recipe pages expose the same recipe data more than once.

Common causes include:

- duplicate JSON-LD blocks
- separate mobile and desktop markup
- multiple Recipe objects
- repeated extraction from overlapping structures

The pipeline removes duplicate ingredients and instructions before later processing.

Comparison normalization may include:

- trimming whitespace
- collapsing repeated whitespace
- case-insensitive comparison
- normalization of common Unicode punctuation

De-duplication must be conservative.

Two similar-looking ingredients or instructions should not be merged unless they are clearly duplicates.

For example:

```text
1 cup flour
1 cup cake flour
```

are distinct ingredients and must remain distinct.

---

## 8. Intermediate Validation

After extraction and structural cleanup, the recipe must pass deterministic validation.

At minimum, a valid intermediate recipe should contain:

- a title
- a source URL
- at least one ingredient
- at least one instruction
- no empty ingredient entries
- no empty instruction entries
- no exact duplicate ingredients
- no exact duplicate instructions

Validation should fail explicitly rather than allowing malformed data to continue through the pipeline.

Typical failures include:

```text
NO_RECIPE_FOUND
EXTRACTION_FAILED
VALIDATION_FAILED
```

This validation boundary ensures downstream transformations operate on a known-good recipe.

---

## 9. Ingredient Normalization

Ingredient processing is responsible for making ingredient text more consistent while preserving recipe meaning.

Possible operations include:

- whitespace cleanup
- fraction normalization
- unit alias normalization
- deterministic unit conversion
- consistent formatting

Examples:

```text
1 tbsp. olive oil
→
1 tbsp olive oil
```

```text
3⁄4 cup sugar
→
3/4 cup sugar
```

Arithmetic and straightforward unit conversion should be deterministic.

Do not use an LLM where normal parsing and conversion logic is sufficient.

Ingredient normalization must not invent quantities or infer missing ingredient amounts.

Ingredient Parser extracts quantities and recognized units. Its Pint-backed
`convert_to` method converts whole larger-unit equivalents: teaspoons to
tablespoons, tablespoons to cups, grams to kilograms, and milliliters to liters.
Fractional quantities remain fractions. Ranges, approximate quantities, and
unrecognized units retain their original measurements. The pipeline does not
infer ingredient density or convert between mass and volume.

Post-processing also removes explicit prices and catalog identifiers from
ingredient lines. Parenthetical preparation details are retained while incidental
notes are removed. Details such as `to taste` and `divided` are retained.
`scripts/normalize_ingredients.py INPUT_DIR OUTPUT_DIR` runs this stage over saved
JSON results. `scripts/test_openai.py` applies the same stage to ingredients when
writing rewritten results.

Product serialization uses Ingredient Parser to split each cleaned ingredient line
into `quantity`, `unit`, `ingredient`, and `preparation_type` fields. Price and catalog
annotations are removed before parsing. The parser's comments, confidence scores,
and other metadata are excluded from product JSON. Cooking notes such as `to taste`
and `for garnish` are retained in `preparation_type`. Extraction output and rewritten
output both use ingredient objects; post-processing scripts also accept older saved
JSON with ingredient strings.

---

## 10. Instruction Rewriting

The instruction-rewriting stage converts source prose into concise cooking instructions.

This is the primary stage where an LLM may be useful.

Example source text:

```text
Preheat the oven to 325°F. Lightly spray an 8x8 baking dish—not a
9x9 dish—with cooking spray. Line it with parchment paper and spray
the parchment.
```

Desired output:

```text
Preheat oven to 325°F. Spray an 8x8 baking dish with cooking spray.
Line with parchment and spray again.
```

The purpose of rewriting is to improve clarity and consistency, not to reinterpret the recipe.

### Preserve

The rewritten recipe must preserve:

- ingredients
- quantities
- temperatures
- durations
- required equipment
- required cooking actions
- meaningful conditions
- step ordering where order matters

### Remove or simplify

The rewriter may remove or simplify:

- unnecessary editorial commentary
- redundant wording
- conversational filler
- irrelevant comparisons
- repeated statements
- source-specific writing style

### Do not invent

The model must not introduce unsupported:

- ingredients
- measurements
- cooking times
- temperatures
- equipment
- techniques
- substitutions
- safety claims

If a rewrite cannot be validated safely, prefer the original extracted instruction.

---

## 11. LLM Boundary

LLM use should remain isolated behind a dedicated interface.

Other pipeline stages should not directly depend on the OpenAI SDK.

Conceptually:

```text
pipeline
   ↓
rewrite interface
   ↓
LLM client
   ↓
OpenAI API
```

This boundary makes it easier to:

- switch models
- change prompts
- benchmark model quality
- track token usage
- mock model responses in tests
- disable LLM processing
- add alternative providers later

Configuration should come from environment variables, such as:

```text
OPENAI_API_KEY
OPENAI_MODEL
```

Secrets must never be committed or logged.

---

## 12. Rewrite Validation

LLM output should not be accepted blindly.

Post-rewrite validation should detect obvious failures such as:

- empty output
- missing temperatures
- missing durations
- missing quantities
- dropped ingredient references
- excessive expansion
- unintended formatting
- malformed instruction structure

Where practical, important values should be compared between source and rewritten instructions.

If validation fails, the pipeline should either:

1. fall back to the original instruction, or
2. fail the transformation explicitly

depending on the severity of the issue.

The pipeline should never silently return a rewrite known to have lost critical information.

---

## 13. Final Recipe JSON

After all stages succeed, the recipe is serialized into the product-facing format.

Example:

```json
{
  "title": "Chocolate Chip Cookies",
  "link": "https://example.com/cookies",
  "ingredients": [
    "2 cups all-purpose flour",
    "2 eggs",
    "1 cup sugar"
  ],
  "recipe": [
    "Preheat oven to 350°F.",
    "Mix flour, eggs, and sugar.",
    "Bake for 12 minutes."
  ]
}
```

The public schema should remain intentionally small and stable.

Implementation details such as:

- extraction method
- parser diagnostics
- retries
- timing
- model token usage
- intermediate representations

should remain internal unless explicitly requested by a benchmark or debug interface.

---

## 14. Diagnostics

The pipeline should expose structured diagnostics internally so failures can be measured and debugged.

Useful fields may include:

```text
source_url
fetch_method
extractor_used
failure_stage
duration_seconds
ingredient_count
instruction_count
duplicate_ingredients
duplicate_instructions
model
input_tokens
output_tokens
cached_input_tokens
```

Diagnostics are primarily for:

- benchmark tooling
- development
- regression analysis
- cost measurement

They are not part of normal product JSON.

---

## 15. Testing Strategy

Each pipeline stage should be testable independently.

### Unit tests

Use unit tests for:

- JSON-LD parsing
- HTML parsing helpers
- structural normalization
- de-duplication
- validation
- ingredient normalization
- unit handling
- rewrite validation

### Integration tests

Use saved fixtures to test complete extraction behavior without requiring live websites.

### Regression tests

When a real recipe page exposes an important bug, reproduce the relevant source structure locally and add a deterministic regression test when practical.

### LLM tests

Do not make the normal deterministic test suite depend on live model calls.

LLM-backed behavior should use:

- mocked responses for normal tests
- fixed evaluation datasets for prompt/model comparisons
- explicit live evaluation commands when needed

---

## 16. Benchmarks

Benchmarks exercise behavior that deterministic tests cannot fully represent.

The standard live benchmark measures performance across a broad set of recipe websites.

The torture benchmark targets difficult cases such as:

- malformed JSON-LD
- multiple Recipe objects
- repeated content
- unusual instruction structures
- slow pages
- blocked requests
- JavaScript-heavy sites
- nested structured data

The torture benchmark is designed to expose failure modes, not estimate typical production success rates.

Pipeline changes should be evaluated at the stage they affect.

For example:

```text
fetch change
→ compare fetch success/failure behavior

extractor change
→ compare extraction success and output structure

rewrite prompt change
→ compare information preservation, prose quality, token usage, and cost
```

---

## 17. Pipeline Invariants

The following should remain true across the pipeline:

1. Source-specific parsing details do not leak into the final product schema.
2. Deterministic stages remain deterministic.
3. The LLM is not used for basic parsing or arithmetic when normal code is sufficient.
4. No stage may silently invent cooking-critical information.
5. Failures remain observable.
6. De-duplication does not aggressively discard legitimate recipe content.
7. Final output conforms to one stable schema.
8. Normal automated tests do not require third-party websites or live model calls.
9. Secrets never appear in source control or logs.

---

## 18. Summary

Recipe Scraper is a staged transformation pipeline:

```text
internet recipe
      ↓
fetch
      ↓
extract
      ↓
normalize
      ↓
de-duplicate
      ↓
validate
      ↓
normalize ingredients
      ↓
rewrite prose
      ↓
validate rewrite
      ↓
consistent recipe JSON
```

Each stage should have one clear responsibility.

The system should favor deterministic behavior wherever possible and use language models only where language understanding or rewriting provides meaningful value.
