# Recipe Rewrite Instructions

Rewrite recipe instructions into concise, direct cooking prose.

## Rules

- Preserve all cooking-critical information.
- Preserve ingredients, quantities, temperatures, times, equipment, actions, conditions, and meaningful ordering.
- Do not invent information.
- Remove unnecessary commentary, repetition, and editorial filler.
- Remove irrelevant warnings or comparisons that do not affect how the recipe is cooked.
- Use short, imperative cooking instructions.
- Keep logically related actions together.
- Do not summarize away useful procedural detail.
- Do not add headings, notes, commentary, or explanations.
- Separate steps with multiple substeps into multiple simpler steps.

## Example
### Input
1. Preheat your oven to 325°F and lightly coat an 8x8-inch baking dish with cooking spray. For easier cleanup and cleaner slices later, line the pan with parchment paper, leaving a little extra hanging over the sides so you can lift the brownies out once they’ve cooled. Give the parchment a quick spray as well to make sure nothing sticks.

### Output
1. Preheat oven to 325°F
2. Lightly coat an 8x8 inch dish with cooking spray, line with parchment, and spray again.


## Output

Return only a valid JSON array of instruction strings.

Do not return Markdown.
Do not wrap the JSON in a code block.