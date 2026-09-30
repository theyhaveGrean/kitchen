# Recipe Rewrite Instructions

Rewrite the supplied recipe steps as concise, direct cooking instructions.

## Requirements

- Preserve ingredients, quantities, temperatures, times, equipment, actions, conditions, and meaningful step order.
- Do not invent details or remove useful procedural information.
- Remove redundant wording, editorial filler, and comparisons that do not affect cooking.
- Use short imperative steps. Split multi-part steps when that makes them easier to follow; keep related actions together.
- Return no headings, notes, or explanations.

## Example

Input:

```text
Preheat your oven to 325°F and lightly coat an 8x8-inch baking dish with cooking spray. For easier cleanup, line it with parchment, leaving overhang to lift the brownies after cooling. Spray the parchment too.
```

Output:

```json
["Preheat oven to 325°F.", "Lightly coat an 8x8-inch dish with cooking spray. Line with parchment and spray again."]
```

## Output format

Return only a valid JSON array of instruction strings. Do not use Markdown or a code fence.
