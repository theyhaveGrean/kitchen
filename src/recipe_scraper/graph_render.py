"""Render a semantic recipe as a rectangular TRN cooking chart."""

from __future__ import annotations

import textwrap
from html import escape

from .graph import RecipeGraph
from .graph_display import build_trn_display_graph
from .graph_layout import Region, build_trn_layout

BACKGROUND = "#f5f5f5"
TEXT = "#242424"
BORDER = "#a4a4a4"
INGREDIENT = "#ffffff"
UNMAPPED = "#ededed"
OPERATION = "#e5e5e5"
GLOBAL = "#dedede"


def graph_debug_text(graph: RecipeGraph) -> str:
    labels = {node.id: f"[{node.type.upper()}] {node.label}" for node in graph.nodes}
    lines = [f"{labels[edge.source]} -> {labels[edge.target]} ({edge.type})" for edge in graph.edges]
    if graph.unresolved_references:
        lines += [f"UNRESOLVED: {item}" for item in graph.unresolved_references]
    if graph.warnings:
        lines += [f"WARNING: {item}" for item in graph.warnings]
    return "\n".join(lines)


def render_svg(graph: RecipeGraph) -> str:
    """Draw precomputed TRN regions; semantic graph data is unchanged."""
    layout = build_trn_layout(build_trn_display_graph(graph))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{layout.width}" height="{layout.height}" '
        f'viewBox="0 0 {layout.width} {layout.height}">',
        f'<rect x="0" y="0" width="{layout.width}" height="{layout.height}" fill="{BACKGROUND}"/>',
        f'<g font-family="Segoe UI, Arial, sans-serif" fill="{TEXT}">',
        f'<rect x="20" y="{min(lane.y for lane in layout.ingredients)}" '
        f'width="{layout.final.x + layout.final.width - 20}" '
        f'height="{max(lane.y + lane.height for lane in layout.ingredients) - min(lane.y for lane in layout.ingredients)}" '
        f'fill="none" stroke="{BORDER}" stroke-width="1.5"/>',
    ]
    parts.append(f'<text x="20" y="34" font-size="16" font-weight="600">'
                 f'{escape(layout.title)}</text>')

    def rectangle(region: Region, fill: str, stroke_width: float = 1) -> None:
        parts.append(
            f'<rect x="{region.x}" y="{region.y}" width="{region.width}" height="{region.height}" '
            f'fill="{fill}" stroke="{BORDER}" stroke-width="{stroke_width}"/>'
        )

    def lines(region: Region, content: str, *, font_size: int = 11, center: bool = False,
              vertical_center: bool = False) -> None:
        chars = max(8, (region.width - 10) // max(5, round(font_size * 0.54)))
        wrapped = textwrap.wrap(content, width=chars, break_long_words=True) or [""]
        line_height = font_size + 2
        first_y = region.y + (region.height - len(wrapped) * line_height) // 2 + font_size if vertical_center else region.y + font_size + 5
        anchor = ' text-anchor="middle"' if center else ""
        x = region.x + region.width // 2 if center else region.x + 5
        for index, line in enumerate(wrapped):
            parts.append(
                f'<text x="{x}" y="{first_y + index * line_height}" font-size="{font_size}"'
                f'{anchor}>{escape(line)}</text>'
            )

    for lane in layout.ingredients:
        rectangle(lane, INGREDIENT if lane.first_operation else UNMAPPED)
        label_area = Region(lane.id, lane.x, lane.y, min(210, lane.width), lane.height, lane.label)
        lines(label_area, lane.label, vertical_center=True)
    for bridge in layout.bridges:
        parts.append(f'<rect x="{bridge.x}" y="{bridge.y}" width="{bridge.width}" '
                     f'height="{bridge.height}" fill="{BORDER}"/>')
    for operation in layout.operations:
        rectangle(operation, OPERATION, 1.3)
        chars = max(6, (operation.width - 8) // 6)
        action_lines = textwrap.wrap(operation.label, width=chars, break_long_words=True)
        detail_text = " · ".join(operation.details)
        if operation.repeated_inputs:
            detail_text += (" · " if detail_text else "") + "+ " + ", ".join(operation.repeated_inputs) + " again"
        detail_lines = textwrap.wrap(detail_text, width=chars, break_long_words=False) if detail_text else []
        total_height = len(action_lines) * 13 + len(detail_lines) * 12
        baseline = operation.y + (operation.height - total_height) // 2 + 11
        center_x = operation.x + operation.width // 2
        for line in action_lines:
            parts.append(f'<text x="{center_x}" y="{baseline}" font-size="11" font-weight="600" '
                         f'text-anchor="middle">{escape(line)}</text>')
            baseline += 13
        for line in detail_lines:
            parts.append(f'<text x="{center_x}" y="{baseline}" font-size="10" '
                         f'text-anchor="middle">{escape(line)}</text>')
            baseline += 12
        for continuation in layout.continuations:
            if continuation.id.startswith(f"continuation_{operation.id}_"):
                parts.append(f'<rect x="{continuation.x - 1}" y="{continuation.y + 1}" '
                             f'width="{continuation.width + 1}" height="{continuation.height - 2}" '
                             f'fill="{OPERATION}"/>')
                for boundary in (operation.y, operation.y + operation.height):
                    if boundary in (continuation.y, continuation.y + continuation.height):
                        parts.append(f'<line x1="{continuation.x - 1}" y1="{boundary}" '
                                     f'x2="{continuation.x + continuation.width}" y2="{boundary}" '
                                     f'stroke="{BORDER}" stroke-width="1.3"/>')
    for global_operation in layout.global_operations:
        rectangle(global_operation, GLOBAL, 1.3)
        lines(global_operation, global_operation.label, font_size=10, center=True, vertical_center=True)
    parts.append("</g></svg>")
    return "".join(parts)
