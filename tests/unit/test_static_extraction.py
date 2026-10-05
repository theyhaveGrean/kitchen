from pathlib import Path
from unittest.mock import patch

import pytest

from recipe_scraper.extractor import extract_recipe
from recipe_scraper.fetch.web import FetchBlocked

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_static_jsonld_success_never_launches_browser():
    html = (FIXTURES / "fx_jsonld_graph.html").read_text(encoding="utf-8")
    with (
        patch(
            "recipe_scraper.extractor.fetch_static",
            return_value=(html, "https://example.test/recipe"),
        ),
        patch("recipe_scraper.extractor.fetch_with_scrapling") as browser,
    ):
        recipe = extract_recipe("https://example.test/recipe")
    browser.assert_not_called()
    assert recipe.metadata["extraction_method"] == "jsonld_static"
    assert not recipe.browser_fallback_used


def test_missing_static_content_can_use_one_browser_fallback():
    html = (FIXTURES / "fx_jsonld_graph.html").read_text(encoding="utf-8")
    with (
        patch(
            "recipe_scraper.extractor.fetch_static",
            return_value=(
                "<html><script src='app.js'></script></html>",
                "https://example.test/recipe",
            ),
        ),
        patch(
            "recipe_scraper.extractor.fetch_with_scrapling",
            return_value=(html, "https://example.test/recipe"),
        ) as browser,
    ):
        recipe = extract_recipe("https://example.test/recipe")
    assert browser.call_count == 1 and recipe.browser_fallback_used
    assert recipe.metadata["extraction_method"] == "jsonld_browser"


def test_explicit_access_denial_does_not_trigger_browser_bypass():
    with (
        patch("recipe_scraper.extractor.fetch_static", side_effect=FetchBlocked("HTTP 403")),
        patch("recipe_scraper.extractor.fetch_with_scrapling") as browser,
    ):
        with pytest.raises(FetchBlocked):
            extract_recipe("https://example.test/recipe")
    browser.assert_not_called()


def test_browser_fallback_can_be_disabled():
    with (
        patch(
            "recipe_scraper.extractor.fetch_static",
            return_value=("<html></html>", "https://example.test/recipe"),
        ),
        patch("recipe_scraper.extractor.fetch_with_scrapling") as browser,
    ):
        with pytest.raises(ValueError):
            extract_recipe("https://example.test/recipe", auto_render_js=False)
    browser.assert_not_called()
