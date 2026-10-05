from unittest.mock import patch

from recipe_scraper.canonical import canonical_from_json
from recipe_scraper.prose_pipeline import faithful_prose, get_prose
from recipe_scraper.semantic import SemanticRecipe


def source():
    canonical = canonical_from_json(
        {
            "title": "Cake",
            "link": "https://example.test/cake",
            "ingredients": ["1 cup flour", "1 cup milk"],
            "recipe": ["Mix flour and milk.", "Bake at 350 F for 20 minutes until golden brown."],
        }
    )
    semantic = SemanticRecipe.model_validate(
        {
            "prep_actions": [],
            "unresolved_references": [],
            "operations": [
                {
                    "id": "op_001",
                    "step_index": 1,
                    "action": "mix",
                    "inputs": ["ing_001", "ing_002"],
                    "output_name": None,
                    "temperature": None,
                    "duration": None,
                    "heat_level": None,
                    "equipment": [],
                    "completion_condition": None,
                    "portions": [],
                },
                {
                    "id": "op_002",
                    "step_index": 2,
                    "action": "bake",
                    "inputs": ["op_001"],
                    "output_name": None,
                    "temperature": "350 F",
                    "duration": "20 minutes",
                    "heat_level": None,
                    "equipment": [],
                    "completion_condition": "until golden brown",
                    "portions": [],
                },
            ],
        }
    )
    return canonical, semantic


def test_default_prose_never_calls_a_model():
    canonical, semantic = source()
    with patch("recipe_scraper.prose_pipeline.rewrite_instructions") as rewrite:
        assert get_prose(canonical, semantic) == [step.text for step in canonical.instructions]
    rewrite.assert_not_called()


def test_lossy_optional_prose_falls_back_and_is_separately_cached(tmp_path):
    canonical, semantic = source()
    original = [step.text for step in canonical.instructions]
    with patch(
        "recipe_scraper.prose_pipeline.rewrite_instructions",
        return_value=["Mix.", "Bake until done."],
    ) as rewrite:
        assert get_prose(canonical, semantic, root=tmp_path, use_llm=True) == original
        assert get_prose(canonical, semantic, root=tmp_path, use_llm=True) == original
    assert rewrite.call_count == 1
    assert not faithful_prose(canonical, semantic, [original[0], "Bake at 375 F for 20 minutes."])


def test_optional_model_failure_keeps_source_prose(tmp_path):
    canonical, semantic = source()
    with patch(
        "recipe_scraper.prose_pipeline.rewrite_instructions", side_effect=ValueError("bad JSON")
    ):
        assert get_prose(canonical, semantic, root=tmp_path, use_llm=True) == [
            step.text for step in canonical.instructions
        ]


def test_optional_prose_cannot_add_cooking_parameters(tmp_path):
    canonical, semantic = source()
    original = [step.text for step in canonical.instructions]
    invented = [original[0], original[1] + " Then rest for 15 minutes."]
    assert not faithful_prose(canonical, semantic, invented)
    with patch("recipe_scraper.prose_pipeline.rewrite_instructions", return_value=invented):
        assert get_prose(canonical, semantic, root=tmp_path, use_llm=True) == original
