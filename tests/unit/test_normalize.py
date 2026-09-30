from recipe_scraper.models import Recipe
from recipe_scraper.normalize import dedupe_recipe_lines, recipe_to_dict


def test_dedupe_recipe_lines_collapses_cosmetic_duplicates():
    values = ["1. Mix well.", "Mix well", "• Bake 20 minutes.", "Bake 20 minutes"]
    assert dedupe_recipe_lines(values) == ["1. Mix well.", "• Bake 20 minutes."]


def test_public_payload_is_intentionally_small():
    recipe = Recipe(
        source_url="https://example.test/r", title=" Test ",
        ingredients=["1 egg", "1 egg"], instructions=["Mix.", "Mix"],
        author="Should not leak", confidence=0.99, extraction_method="json-ld",
    )
    assert recipe_to_dict(recipe) == {
        "title": "Test",
        "link": "https://example.test/r",
        "ingredients": [{"quantity": "1", "unit": None, "ingredient": "egg", "preparation_type": None}],
        "recipe": ["Mix."],
    }
