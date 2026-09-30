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

Semantic cooking graphs use the separate [RecipeGraph schema](graph.md) and are cached outside product recipe JSON.
