Create a directed cooking material-flow graph from the supplied structured recipe JSON. Use semantic reasoning to resolve references and dependencies. Return only the RecipeGraph schema.

The input provides ingredient IDs, parsed ingredient fields, optional original ingredient text, and numbered rewritten instructions. Use those exact ingredient IDs and names. For each source ingredient, create exactly one ingredient node with matching quantity, unit, preparation, and original_text. Use null when input lacks a value. Do not invent ingredients or quantities.

Create operation nodes for meaningful cooking actions. The operation label can be any short action; do not limit it to a fixed vocabulary. Set step_index to the one-based instruction number and source_instruction to that instruction's exact text. Include temperature, duration, and heat_level when stated; otherwise use null.

The graph will naturally map ingredients to cooking actions so do not include ingredients or the dish itself in the actions. For example, "Bake Ziti" can be shortened to just "Bake" and "Mix Ricotta Filling" can be shortened to just "Mix".

Create intermediate nodes for prepared products: chopped onion, sauce, marinade, batter, dough, cooked chicken, and similar results. Create exactly one final node for the prepared dish after its last operation. The final node has no outgoing edges. Every intermediate and final product must have exactly one incoming output edge from its producing operation. Use input edges from ingredient or intermediate nodes to operations, output edges from operations to products, and dependency edges between operations when an action has no material output (for example preheating before baking). If a finished dish is plated or served later, represent the pre-serving dish as an intermediate and the plated dish as final.

Model actual flow, not a chain of instruction numbers. Support parallel branches, reserved or divided ingredients, later additions, toppings, separate sauce or marinade, and reuse of a prepared item. An ingredient node can have multiple outgoing input edges when divided or reused. Do not create a cycle. Connect every definite branch to the final dish. Report genuine uncertainty in unresolved_references and warnings without guessing a connection.

For non-ingredient nodes, ingredient_id, quantity, unit, preparation, and original_text must be null. For ingredient and product nodes, step_index and operation metadata must be null. Use unique IDs with prefixes ingredient_, op_, intermediate_, and final_. Keep labels concise and specific.
