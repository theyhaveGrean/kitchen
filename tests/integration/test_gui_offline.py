"""The real PyQt UI renders saved canonical/semantic artifacts without API calls."""

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt6")

from PyQt6.QtGui import QFontDatabase  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from recipe_scraper.canonical import canonical_from_json  # noqa: E402
from recipe_scraper.semantic_pipeline import semantic_cache_key  # noqa: E402
from scripts import compare_results  # noqa: E402


def test_ui_uses_source_graph_and_table_without_a_presentation_file(tmp_path, monkeypatch):
    case = json.loads(
        (Path(__file__).parents[1] / "fixtures/semantic_cases.json").read_text(encoding="utf-8")
    )[1]
    canonical = canonical_from_json(case["recipe"])
    for name in ("LATEST_DIR", "REWRITTEN_DIR", "GRAPH_DIR", "CANONICAL_DIR", "SEMANTIC_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(compare_results, name, directory)
    filename = "cake.json"
    (compare_results.LATEST_DIR / filename).write_text(
        json.dumps(canonical.product_json()), encoding="utf-8"
    )
    (compare_results.CANONICAL_DIR / filename).write_text(
        canonical.model_dump_json(), encoding="utf-8"
    )
    (compare_results.GRAPH_DIR / filename).with_suffix(".semantic.json").write_text(
        json.dumps(
            {
                "cache_key": semantic_cache_key(canonical),
                "semantic": case["semantic"],
                "provenance": {},
            }
        ),
        encoding="utf-8",
    )
    app = QApplication.instance() or QApplication([])
    # Qt's Windows offscreen plugin has no system font database. Register the
    # installed UI font for a representative preview without copying font files.
    if not QFontDatabase.families():
        font = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/segoeui.ttf"
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    window = compare_results.ResultsWindow()
    try:
        app.processEvents()
        renderer = window.graph_svg.renderer()
        assert renderer is not None and renderer.isValid()
        assert "Fold" in window.table_view.toPlainText()
        assert "cached semantics" in window.graph_status.text()
        assert window.graph_button.isEnabled()
        assert window.graph_debug.isHidden()
        assert "op_001" in window.graph_debug.toPlainText()
        assert window.graph_svg.grab().save(str(tmp_path / "graph.png"))
    finally:
        window.close()
