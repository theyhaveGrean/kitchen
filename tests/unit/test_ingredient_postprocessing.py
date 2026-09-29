from recipe_scraper.ingredient_cleanup import clean_all


def test_cleanup_removes_prices_and_side_notes_but_keeps_amount_and_name() -> None:
    assert clean_all([
        "1 lb chicken breast - $8.99",
        "2 tbsp olive oil (optional)",
        "3 cups chopped tomatoes, divided",
    ]) == ["1 lb chicken breast", "2 tbsp olive oil", "3 cups chopped tomatoes, divided"]


def test_cleanup_retains_parenthetical_preparation() -> None:
    assert clean_all(["2 onions (finely chopped)", "1 lb chicken (6 pieces)"]) == [
        "2 onions, finely chopped", "1 lb chicken",
    ]
