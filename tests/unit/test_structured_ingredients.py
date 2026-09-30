from recipe_scraper.structured_ingredients import (
    ingredient_to_line,
    parse_ingredient_line,
    parse_ingredients,
)


def test_parse_ingredient_keeps_preparation_and_discards_comment() -> None:
    assert parse_ingredient_line("3 pounds pork shoulder, cut into 2-inch chunks") == {
        "quantity": "3",
        "unit": "lb",
        "ingredient": "pork shoulder",
        "preparation_type": "cut into 2 inch chunks",
    }


def test_unmeasured_ingredient_keeps_cooking_note() -> None:
    assert parse_ingredient_line("salt to taste") == {
        "quantity": None,
        "unit": None,
        "ingredient": "salt",
        "preparation_type": "to taste",
    }


def test_structured_ingredient_can_be_reprocessed() -> None:
    item = parse_ingredient_line("2 cups flour, sifted")
    assert ingredient_to_line(item) == "2 cup flour, sifted"


def test_number_at_end_of_name_is_not_a_second_amount() -> None:
    assert parse_ingredient_line("1 cup ingredient 1") == {
        "quantity": "1",
        "unit": "cup",
        "ingredient": "ingredient 1",
        "preparation_type": None,
    }


def test_parser_normalizes_exact_larger_units() -> None:
    examples = {
        "3 tsp salt": ("1", "tbsp"),
        "16 tbsp oil": ("1", "cup"),
        "48 tsp water": ("1", "cup"),
        "1000 g flour": ("1", "kg"),
        "1000 mL water": ("1", "L"),
    }
    for line, expected in examples.items():
        parsed = parse_ingredient_line(line)
        assert (parsed["quantity"], parsed["unit"]) == expected


def test_parser_keeps_fraction_range_and_ounce_kind() -> None:
    assert parse_ingredient_line("0.5 tsp salt")["quantity"] == "1/2"
    assert parse_ingredient_line("3-4 tsp oil")["quantity"] == "3-4"
    assert parse_ingredient_line("1 oz cheese")["unit"] == "oz"
    assert parse_ingredient_line("1 fl oz juice")["unit"] == "fl oz"


def test_parser_handles_parenthetical_preparation_and_multiple_amounts() -> None:
    assert parse_ingredient_line("2 onions (finely chopped)") == {
        "quantity": "2",
        "unit": None,
        "ingredient": "onions",
        "preparation_type": "finely chopped",
    }
    assert parse_ingredient_line("1 lb chicken (6 pieces)") == {
        "quantity": "1 lb, 6 pieces",
        "unit": None,
        "ingredient": "chicken",
        "preparation_type": None,
    }


def test_batch_parser_removes_shopping_annotations() -> None:
    lines = [
        "1 lb chicken breast - $8.99",
        "2 cups flour (SKU: 123)",
        "15 oz ricotta ($3.39)",
        "1/4 tsp freshly cracked black pepper ($0.05)",
        "1 handful chopped parsley (optional, for garnish) ($0.20)",
    ]
    assert parse_ingredients(lines) == [parse_ingredient_line(line) for line in lines]
    assert parse_ingredients(lines)[2:] == [
        {"quantity": "15", "unit": "oz", "ingredient": "ricotta", "preparation_type": None},
        {
            "quantity": "1/4",
            "unit": "tsp",
            "ingredient": "black pepper",
            "preparation_type": "freshly cracked",
        },
        {
            "quantity": "1",
            "unit": "handful",
            "ingredient": "parsley",
            "preparation_type": "chopped, for garnish",
        },
    ]
