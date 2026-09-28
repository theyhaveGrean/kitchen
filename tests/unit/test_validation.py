from bs4 import BeautifulSoup

from recipe_scraper.models import Recipe
from recipe_scraper.validation import looks_like_recipe_roundup


def complete_recipe(title: str) -> Recipe:
    return Recipe(title=title, ingredients=["a", "b"], instructions=["do a", "do b"], extraction_method="json-ld")


def test_numbered_roundup_with_multiple_recipes_is_rejected():
    soup = BeautifulSoup("<html><h1>35 Chicken Breast Recipes</h1></html>", "lxml")
    assert looks_like_recipe_roundup(
        soup, [complete_recipe("A"), complete_recipe("B")], "https://example.test/recipes-menus/chicken/"
    )


def test_normal_recipe_is_not_rejected():
    soup = BeautifulSoup("<html><h1>Chicken Curry</h1></html>", "lxml")
    assert not looks_like_recipe_roundup(soup, [complete_recipe("Chicken Curry")], "https://example.test/chicken-curry")
