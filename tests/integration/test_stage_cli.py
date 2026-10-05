"""Compile and inspect saved source/semantic artifacts without mocks or APIs."""

import json
from pathlib import Path

from recipe_scraper.canonical import canonical_from_json
from recipe_scraper.stage_cli import main

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/semantic_cases.json").read_text(encoding="utf-8")
)


def test_saved_artifacts_validate_compile_and_render_offline(tmp_path):
    case = CASES[1]
    artifact = tmp_path / "semantic.json"
    artifact.write_text(
        json.dumps(
            {
                "canonical": canonical_from_json(case["recipe"]).model_dump(),
                "semantic": case["semantic"],
            }
        ),
        encoding="utf-8",
    )
    issues = tmp_path / "issues.json"
    assert main(["validate", str(artifact), "-o", str(issues)]) == 0
    assert json.loads(issues.read_text())["valid"]
    graph, svg, table = (
        tmp_path / filename for filename in ("graph.json", "graph.svg", "table.html")
    )
    assert (
        main(["graph", str(artifact), "-o", str(graph), "--svg", str(svg), "--table", str(table)])
        == 0
    )
    assert json.loads(graph.read_text())["nodes"]
    assert "<svg" in svg.read_text(encoding="utf-8")
    assert "rowspan" in table.read_text(encoding="utf-8")


def test_extract_fixture_preserves_raw_ingredients_and_source_steps(tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures/fx_jsonld_graph.html"
    output = tmp_path / "canonical.json"
    assert main(["extract", str(fixture), "--html-file", "-o", str(output)]) == 0
    canonical = json.loads(output.read_text(encoding="utf-8"))
    assert canonical["ingredients"][0]["original_text"]
    assert canonical["ingredients"][0]["id"] == "ing_001"
    assert canonical["instructions"][0]["index"] == 1


def test_invalid_semantics_emit_issues_without_a_graph(tmp_path):
    case = CASES[0]
    semantic = json.loads(json.dumps(case["semantic"]))
    semantic["operations"][0]["inputs"] = ["ing_999"]
    artifact = tmp_path / "invalid.json"
    artifact.write_text(
        json.dumps(
            {"canonical": canonical_from_json(case["recipe"]).model_dump(), "semantic": semantic}
        )
    )
    output = tmp_path / "issues.json"
    assert main(["validate", str(artifact), "-o", str(output)]) == 1
    assert not json.loads(output.read_text())["valid"]
    graph = tmp_path / "graph.json"
    assert main(["graph", str(artifact), "-o", str(graph)]) == 1
    assert not graph.exists()
