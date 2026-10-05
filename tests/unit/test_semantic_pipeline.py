import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from recipe_scraper.canonical import canonical_from_json
from recipe_scraper.conversion import convert_canonical
from recipe_scraper.llm import (
    SemanticResponse,
    infer_semantic_recipe,
    inference_tiers,
    semantic_input,
)
from recipe_scraper.semantic import SemanticRecipe
from recipe_scraper.semantic_pipeline import (
    SemanticInferenceFailure,
    get_semantic,
    semantic_cache_key,
)

CASE = json.loads(
    (Path(__file__).parents[1] / "fixtures/semantic_cases.json").read_text(encoding="utf-8")
)[0]


def response():
    return SemanticResponse(SemanticRecipe.model_validate(CASE["semantic"]), "luna", "low", 100, 40)


def test_one_call_for_valid_semantics_then_no_calls_on_cache_hit(tmp_path):
    canonical = canonical_from_json(CASE["recipe"])
    with patch(
        "recipe_scraper.semantic_pipeline.infer_semantic_recipe", return_value=response()
    ) as infer:
        first = convert_canonical(canonical, root=tmp_path)
        second = convert_canonical(canonical, root=tmp_path)
    assert infer.call_count == 1 and not first.inference.cached and second.inference.cached
    assert first.graph == second.graph
    assert first.inference.provenance["output_tokens"] == 40
    assert first.inference.provenance["repair_attempts"] == 0
    assert "source_instruction" not in semantic_input(canonical)


def test_validation_failure_uses_repair_tier_and_preserves_previous(tmp_path):
    canonical = canonical_from_json(CASE["recipe"])
    invalid = response()
    invalid.semantic.operations[0].temperature = "375 F"
    with patch(
        "recipe_scraper.semantic_pipeline.infer_semantic_recipe", side_effect=[invalid, response()]
    ) as infer:
        result = get_semantic(canonical, tmp_path / "semantic.json")
    assert infer.call_count == 2
    args = infer.call_args.args
    assert args[1] == inference_tiers()[1]
    assert args[2] == invalid.semantic
    assert any(issue["code"] == "INVENTED_TEMPERATURE" for issue in args[3])
    assert result.provenance["repair_attempts"] == 1


def test_compiler_change_rebuilds_artifact_without_another_model_call(tmp_path, monkeypatch):
    from recipe_scraper.graph_pipeline import get_or_generate_graph

    monkeypatch.setenv("RECIPE_CACHE_DIR", str(tmp_path / "cache"))
    path = tmp_path / "graph.json"
    with patch(
        "recipe_scraper.semantic_pipeline.infer_semantic_recipe", return_value=response()
    ) as infer:
        first, _, first_cached = get_or_generate_graph(path, CASE["recipe"])
        first_record = json.loads(path.read_text(encoding="utf-8"))
        monkeypatch.setattr("recipe_scraper.graph_pipeline.GRAPH_COMPILER_VERSION", "next-version")
        second, _, second_cached = get_or_generate_graph(path, CASE["recipe"])
    second_record = json.loads(path.read_text(encoding="utf-8"))
    assert infer.call_count == 1 and not first_cached and second_cached
    assert first == second
    assert second_record["compiler_version"] == "next-version"
    assert first_record["cache_key"] != second_record["cache_key"]


def test_schema_failure_gets_one_repair_attempt(tmp_path):
    with pytest.raises(ValidationError) as error:
        SemanticRecipe.model_validate({"operations": "bad"})
    canonical = canonical_from_json(CASE["recipe"])
    with patch(
        "recipe_scraper.semantic_pipeline.infer_semantic_recipe",
        side_effect=[error.value, response()],
    ) as infer:
        get_semantic(canonical, tmp_path / "semantic.json")
    assert infer.call_count == 2
    assert infer.call_args.args[2] is None
    assert infer.call_args.args[3][0]["code"] == "INVALID_SCHEMA"


def test_invalid_repairs_fail_explicitly_and_never_cache(tmp_path):
    canonical = canonical_from_json(CASE["recipe"])
    invalid = response()
    invalid.semantic.operations[0].inputs = []
    path = tmp_path / "semantic.json"
    with patch(
        "recipe_scraper.semantic_pipeline.infer_semantic_recipe", return_value=invalid
    ) as infer:
        with pytest.raises(SemanticInferenceFailure) as failure:
            get_semantic(canonical, path)
    assert infer.call_count == 2 and not path.exists()
    assert failure.value.attempts == 2
    assert failure.value.as_dict()["issues"]


def test_transport_failures_do_not_trigger_semantic_repair(tmp_path):
    with patch(
        "recipe_scraper.semantic_pipeline.infer_semantic_recipe",
        side_effect=ConnectionError("offline"),
    ) as infer:
        with pytest.raises(ConnectionError):
            get_semantic(canonical_from_json(CASE["recipe"]), tmp_path / "semantic.json")
    assert infer.call_count == 1


def test_model_config_changes_semantic_cache_key(monkeypatch):
    canonical = canonical_from_json(CASE["recipe"])
    before = semantic_cache_key(canonical)
    monkeypatch.setenv("OPENAI_REPAIR_MODEL", "stronger-configured-model")
    assert semantic_cache_key(canonical) != before


def test_api_enforces_semantics_and_sends_structured_repair_issues():
    canonical = canonical_from_json(CASE["recipe"])
    with patch("recipe_scraper.llm._client") as client:
        reply = client.return_value.responses.parse.return_value
        reply.status = "completed"
        reply.output_parsed = response().semantic
        reply.model = "luna"
        reply.usage = None
        infer_semantic_recipe(
            canonical, inference_tiers()[1], response().semantic, [{"code": "INVALID_SCHEMA"}]
        )
    kwargs = client.return_value.responses.parse.call_args.kwargs
    assert kwargs["text_format"] is SemanticRecipe
    assert "INVALID_SCHEMA" in kwargs["input"][-1]["content"]
    assert "Previous" in kwargs["input"][-1]["content"]
