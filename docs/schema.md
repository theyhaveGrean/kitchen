# Recipe Schema

Successful output has exactly four top-level fields. Extraction metadata and parser diagnostics are internal.

```json
{
  "title": "Chocolate Chip Cookies",
  "link": "https://example.com/chocolate-chip-cookies",
  "ingredients": [
    {"quantity": "2", "unit": "cups", "ingredient": "all-purpose flour", "preparation_type": null},
    {"quantity": "1/2", "unit": "tsp", "ingredient": "salt", "preparation_type": null},
    {"quantity": null, "unit": null, "ingredient": "fresh parsley", "preparation_type": "chopped"}
  ],
  "recipe": ["Mix the ingredients.", "Bake for 12 minutes."]
}
```

| Field | Required value |
| --- | --- |
| `title` | Non-empty, human-readable string |
| `link` | Non-empty source URL without Markdown |
| `ingredients` | Non-empty ordered array of ingredient objects |
| `recipe` | Non-empty array of actionable instruction strings |

Each ingredient object has exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `quantity` | string or null | Amount, fraction, or range as provided |
| `unit` | string or null | Unit when separable from the amount |
| `ingredient` | non-empty string | Ingredient name and relevant size descriptors |
| `preparation_type` | string or null | Preparation required by the ingredient line |

Do not invent amounts. Without an amount, `quantity` and `unit` are `null`. Keep composite measurements in `quantity` with `unit: null` when they cannot be represented as one amount and unit. Remove exact accidental duplicates, but preserve similar ingredients with different amounts or preparations. Keep source order and cooking-critical preparation details.

Instructions preserve ingredients, quantities, temperatures, times, equipment, required actions, and meaningful sequence; remove clear duplicate instructions. Prices, catalog IDs, comments, confidence scores, and other parser metadata are excluded. Top-level values and lists cannot be null or empty. The schema has no version field.

Internally, extractors may retain raw ingredient strings. Serialization parses cleaned strings into ingredient objects. Post-processing also accepts legacy saved JSON with string ingredients, but emits this canonical schema.

## Internal CanonicalRecipe

The four-field product format above remains a compatibility/presentation format. Source ingestion and AI input now use the versioned internal `CanonicalRecipe`.

| Field | Meaning |
| --- | --- |
| `title`, `source_url`, `canonical_url` | Source identity; URLs may be null for local imports. |
| `ingredients` | Source-ordered ingredients with stable `ing_001` IDs, immutable-original `original_text`, advisory nullable `name`, `quantity`, `unit`, `preparation`, and optional parsed data. |
| `instructions` | Consecutive one-based `{index, text}` source steps. |
| `yield_text`, `prep_time`, `cook_time`, `total_time` | Source metadata when available. |
| `metadata` | Diagnostics/provenance, separate from meaningful source content and product data. |

Original ingredient text is never overwritten by parsed values. Parser failures preserve original text with null parsed fields. Legacy four-field JSON imports are supported; reconstructed originals are explicitly marked in metadata.

## SemanticRecipe

The AI emits only `prep_actions`, `operations`, and `unresolved_references`. Each operation has a sequential `op_001` ID, `step_index`, concise lowercase `action`, ingredient/earlier-operation `inputs`, optional `output_name`, optional source phrases for `temperature`, `duration`, `heat_level`, and `completion_condition`, explicit important `equipment`, and source-worded `portions` (`ref`, `text`). No labels, source-instruction copies, ingredients, graph nodes, edges, or layout are generated.

Prep actions have the same source parameter fields plus an `ingredients` array identifying canonical supplies they consume. They have no material output or model-assigned IDs. Model optional fields are required JSON keys with null or empty arrays when absent, matching provider strict structured output.

Operations may share an instruction index and branch/merge. Inputs may reuse a canonical ingredient or earlier material output with portion metadata; canonical ingredients are never duplicated. An operation has exactly one implicit material output. The normal supported recipe has one terminal material stream. Unknown references, forward references, cycles, invented parameters, duplicate IDs/actions, invalid source steps, empty material inputs, and unsupported material products are rejected with structured issues.

Compiled cooking graphs use the separate [RecipeGraph schema](graph.md), outside product recipe JSON. Model, prompt/schema versions, reasoning, timestamps, token usage, repair counts, and validation status are sidecar provenance rather than semantic fields.
