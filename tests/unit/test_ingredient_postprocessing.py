from recipe_scraper.ingredient_cleanup import clean_all


def test_cleanup_removes_shopping_annotations_only() -> None:
    assert clean_all([
        "1 lb chicken breast - $8.99",
        "2 tbsp olive oil (optional)",
        "15 oz ricotta ($3.39)",
        "2 cups flour (SKU: 123)",
        "2 onions (finely chopped)",
    ]) == [
        "1 lb chicken breast",
        "2 tbsp olive oil (optional)",
        "15 oz ricotta ($3.39)",
        "2 cups flour",
        "2 onions (finely chopped)",
    ]
