"""Deterministic prose and compact material tables; semantics never choose layout."""

from __future__ import annotations

import re
from html import escape

from .canonical import CanonicalRecipe
from .semantic import SemanticRecipe
from .semantic_topology import can_render_as_table, ingredient_groups

PRESENTATION_VERSION = "source-prose-table-v1"


def render_prose(canonical: CanonicalRecipe, semantic: SemanticRecipe) -> list[str]:
    """Conservative formatting keeps every cooking-critical clause from the source."""
    # Semantic prose synthesis can discard actions not modeled as material flow.
    # Preserve source clauses; compact action sentences live in the table instead.
    return [re.sub(r"^\s*\d+[.)]\s+", "", step.text).strip() for step in canonical.instructions]


def render_table(canonical: CanonicalRecipe, semantic: SemanticRecipe) -> str | None:
    """One row per ingredient with merged action cells; nonlaminar flow uses TRN."""
    if not can_render_as_table(semantic):
        return None
    groups = ingredient_groups(semantic)
    # Order leaf ingredients so every laminar group is a contiguous row span.
    ingredient_ids = [item.id for item in canonical.ingredients]
    clusters = sorted(
        {frozenset(group) for group in groups.values()},
        key=lambda group: (-len(group), sorted(group)),
    )
    for cluster in clusters:
        inside = [ref for ref in ingredient_ids if ref in cluster]
        if inside:
            start = min(ingredient_ids.index(ref) for ref in inside)
            ingredient_ids = [ref for ref in ingredient_ids if ref not in cluster]
            ingredient_ids[start:start] = inside
    positions = {ref: i for i, ref in enumerate(ingredient_ids)}
    if any(
        max(positions[ref] for ref in group) - min(positions[ref] for ref in group) + 1
        != len(group)
        for group in groups.values()
    ):
        return None
    items = {item.id: item for item in canonical.ingredients}
    rows: list[str] = []
    for index, ingredient_id in enumerate(ingredient_ids):
        cells = [f"<th>{escape(items[ingredient_id].original_text)}</th>"]
        for op in semantic.operations:
            group = groups[op.id]
            first = min(positions[ref] for ref in group)
            if index == first:
                details = " · ".join(
                    value for value in (op.temperature, op.duration, op.heat_level) if value
                )
                cells.append(
                    f'<td rowspan="{len(group)}"><strong>{escape(op.action.capitalize())}</strong>'
                    + (f"<br>{escape(details)}" if details else "")
                    + "</td>"
                )
            elif ingredient_id not in group:
                cells.append('<td class="empty"></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    headers = "".join(
        f"<span>{escape(prep.action.capitalize())}</span> " for prep in semantic.prep_actions
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>'
        "body{font:14px system-ui;color:#111;background:#fff}table{border-collapse:collapse}"
        "th,td{padding:8px;text-align:center;border:1px solid #777}th{text-align:left}"
        ".empty{border:none}span{display:inline-block;padding:6px}</style></head><body>"
        f"<h1>{escape(canonical.title)}</h1>{headers}<table>"
        + "".join(rows)
        + "</table></body></html>"
    )
