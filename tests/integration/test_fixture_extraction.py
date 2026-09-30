from __future__ import annotations

import csv
from pathlib import Path

import pytest

from benchmarks.batch import meets_expectations
from recipe_scraper import extract_from_html
from recipe_scraper.normalize import recipe_to_dict

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "benchmarks/datasets/torture_50.csv"


def fixture_cases():
    rows = []
    with DATASET.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if (row.get("test_kind") or "").casefold() == "fixture":
                rows.append(row)
    return rows


@pytest.mark.integration
@pytest.mark.parametrize("row", fixture_cases(), ids=lambda r: r["id"])
def test_torture_fixture(row):
    fixture = (ROOT / row["url_or_fixture"]).resolve()
    html = fixture.read_text(encoding="utf-8")
    recipe = extract_from_html(html, fixture.as_uri())
    expected_reject = (row.get("expected_outcome") or "pass").casefold() in {"reject", "reject_or_unsupported"}
    if expected_reject:
        assert recipe is None
        return
    assert recipe is not None
    payload = recipe_to_dict(recipe, include_debug=True)
    ok, error = meets_expectations(row, payload)
    assert ok, error
