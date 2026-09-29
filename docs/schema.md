# Recipe Schema

Successful recipe JSON has four top-level fields: `title`, `link`, `ingredients`,
and `recipe`. Extraction metadata and parser diagnostics stay outside product JSON.

```json
{
  "title": "Chocolate Chip Cookies",
  "link": "https://example.com/chocolate-chip-cookies",
  "ingredients": [
    {
      "quantity": "2",
      "unit": "cups",
      "ingredient": "all-purpose flour",
      "preparation_type": null
    },
    {
      "quantity": "1/2",
      "unit": "tsp",
      "ingredient": "salt",
      "preparation_type": null
    },
    {
      "quantity": null,
      "unit": null,
      "ingredient": "fresh parsley",
      "preparation_type": "chopped"
    }
  ],
  "recipe": ["Mix the ingredients.", "Bake for 12 minutes."]
}
```

`title` is a non-empty human-readable string. `link` is a non-empty source URL,
with no Markdown syntax. `recipe` is a non-empty array of actionable instruction
strings. Instructions preserve ingredients, quantities, temperatures, times,
equipment, required actions, and sequence. Clear duplicate instructions are removed.

`ingredients` is a non-empty array of objects. Each object has exactly these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `quantity` | string or null | Exact amount, fraction, or range when provided |
| `unit` | string or null | Unit attached to the amount when it can be represented separately |
| `ingredient` | non-empty string | Ingredient name, including relevant size descriptors |
| `preparation_type` | string or null | Preparation required by the ingredient line |

The parser does not invent missing amounts. A line without an amount has `null`
for `quantity` and `unit`. Composite or multiple measurements are retained as
text in `quantity` with `unit: null` when they cannot be expressed as one amount
and one unit. Exact accidental duplicate ingredient lines are removed before
parsing. Similar ingredients with different quantities or preparations stay separate.

Prices, catalog IDs, comments, and parser confidence scores are omitted. Ingredient
order follows the source. Parsing must retain cooking-critical preparation details.

The internal extraction model can keep raw ingredient strings. Product serialization
parses them into the object form above. Saved legacy JSON with string ingredients
can still be passed to the post-processing scripts; their output uses this schema.

Empty titles, links, ingredient lists, instruction lists, or ingredient names make a
recipe invalid. Top-level fields are never `null`. The schema has no version field.
