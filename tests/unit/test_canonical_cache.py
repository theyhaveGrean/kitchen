import json
from unittest.mock import patch

import pytest

from recipe_scraper.cache import (
    content_hash,
    normalize_url,
    page_canonical_url,
    read_record,
    write_record,
)
from recipe_scraper.canonical import canonical_from_json, canonicalize
from recipe_scraper.conversion import extract_canonical
from recipe_scraper.models import Recipe
from recipe_scraper.semantic_pipeline import semantic_cache_key


def source_recipe():
    return Recipe(
        title="Soup",
        source_url="https://example.test/soup",
        ingredients=["1 carrot (optional)", "2 cups water"],
        instructions=["Chop carrot.", "Simmer carrot in water until tender."],
    )


def test_canonical_keeps_source_text_and_deterministic_ids():
    recipe = source_recipe()
    canonical = canonicalize(recipe)
    assert [item.id for item in canonical.ingredients] == ["ing_001", "ing_002"]
    assert canonical.ingredients[0].original_text == "1 carrot (optional)"
    assert [step.text for step in canonical.instructions] == recipe.instructions
    assert canonicalize(recipe) == canonical


def test_failed_advisory_parsing_does_not_destroy_source():
    with patch(
        "recipe_scraper.canonical.parse_ingredient_line", side_effect=RuntimeError("parser missing")
    ):
        canonical = canonicalize(source_recipe())
    assert all(item.name is None and item.parsed is None for item in canonical.ingredients)
    assert canonical.ingredients[0].original_text == "1 carrot (optional)"
    assert canonical.product_json()["ingredients"][0]["ingredient"] == "1 carrot (optional)"


def test_tracking_urls_share_cache_but_recipe_queries_do_not():
    assert (
        normalize_url("https://EXAMPLE.test:443/r/?utm_source=a#steps") == "https://example.test/r"
    )
    assert normalize_url("https://example.test/r?recipe=1") != normalize_url(
        "https://example.test/r?recipe=2"
    )
    assert normalize_url("https://example.test/r?portion=1&portion=2") != normalize_url(
        "https://example.test/r?portion=2&portion=1"
    )
    assert (
        page_canonical_url('<link rel="canonical" href="/soup/">', "https://example.test/r")
        == "https://example.test/soup"
    )
    assert (
        page_canonical_url(
            '<link rel="canonical" href="https://other.test/soup">', "https://example.test/r"
        )
        == "https://example.test/r"
    )


def test_cache_records_are_atomic_and_corruption_is_a_miss(tmp_path):
    path = tmp_path / "record.json"
    write_record(path, {"cache_key": "one", "value": 1})
    assert read_record(path, "one")["value"] == 1
    assert read_record(path, "two") is None
    assert read_record(path, "one", ttl=0) is None
    path.write_text("[]")
    assert read_record(path, "one") is None
    assert not list(tmp_path.glob("*.tmp"))


def test_prompt_changes_do_not_invalidate_extraction_cache(tmp_path, monkeypatch):
    with patch("recipe_scraper.conversion.extract_recipe", return_value=source_recipe()) as fetch:
        first = extract_canonical("https://example.test/soup?utm_source=a", root=tmp_path)
        first_key = semantic_cache_key(first)
        prompt = tmp_path / "prompt.md"
        prompt.write_text("Changed inference prompt")
        monkeypatch.setattr("recipe_scraper.semantic_pipeline.SEMANTIC_PROMPT", prompt)
        second = extract_canonical("https://example.test/soup/#steps", root=tmp_path)
        assert fetch.call_count == 1
    assert semantic_cache_key(second) != first_key
    assert second.metadata["extraction_cache_hit"]


def test_semantic_hash_ignores_diagnostics_but_tracks_source():
    canonical = canonicalize(source_recipe())
    before = semantic_cache_key(canonical)
    canonical.metadata["fetch_ms"] = 300
    canonical.ingredients[0].parsed = {"confidence": 0.5}
    assert semantic_cache_key(canonical) == before
    canonical.instructions[0].text = "Slice carrot."
    assert semantic_cache_key(canonical) != before


def test_product_import_validates_original_alignment():
    data = {
        "title": "Soup",
        "link": "https://example.test/soup",
        "ingredients": ["1 carrot"],
        "recipe": ["Chop carrot."],
    }
    with pytest.raises(ValueError, match="align"):
        canonical_from_json(data, [])
    canonical = canonical_from_json(data)
    assert canonical.ingredients[0].original_text == "1 carrot"
    assert content_hash(json.loads(canonical.model_dump_json()))
