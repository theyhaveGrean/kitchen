"""Deterministic rectangular TRN geometry from a display-only recipe graph."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from .graph_display import TRNDisplayGraph

LEFT = 20
LABEL_WIDTH = 210
HEADER_TOP = 48
ROW_MIN_HEIGHT = 24
ALIGN_TOLERANCE = 24


@dataclass(frozen=True)
class Region:
    id: str
    x: int
    y: int
    width: int
    height: int
    label: str = ""


@dataclass(frozen=True)
class IngredientLane(Region):
    row: int = 0
    first_operation: str | None = None


@dataclass(frozen=True)
class OperationRegion(Region):
    step_index: int | None = None
    details: tuple[str, ...] = ()
    repeated_inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class TRNLayout:
    width: int
    height: int
    title: str
    ingredients: tuple[IngredientLane, ...]
    operations: tuple[OperationRegion, ...]
    continuations: tuple[Region, ...]
    bridges: tuple[Region, ...]
    global_operations: tuple[Region, ...]
    final: Region


def _operation_width(label: str, details: tuple[str, ...]) -> int:
    """Fit action words first, allowing a little width for multiword details."""
    longest_word = max((len(word) for word in label.split()), default=0)
    longest_detail = max((len(word) for detail in details for word in detail.split()), default=0)
    metadata_length = len(" ".join(details))
    return max(48, min(110, round(max(25 + len(label) * 2, longest_word * 6.5 + 10,
                                   min(longest_detail, 9) * 5.2 + 8,
                                   48 + max(0, metadata_length - 20) * 0.55))))


def _text_height(label: str, details: tuple[str, ...], width: int) -> int:
    chars = max(6, (width - 8) // 6)
    action = textwrap.wrap(label, width=chars, break_long_words=True)
    metadata = textwrap.wrap(" · ".join(details), width=chars, break_long_words=False)
    return len(action) * 13 + len(metadata) * 12 + 8


def build_trn_layout(display: TRNDisplayGraph) -> TRNLayout:
    """Place input rows, operation stages, process continuations, and headers."""
    operations = display.operations
    stage_index = {operation.id: index for index, operation in enumerate(operations)}
    first_use: dict[str, int] = {}
    direct_consumers: dict[str, list[str]] = {}
    for ingredient in display.inputs:
        consumers = sorted(ingredient.consumers, key=stage_index.__getitem__)
        direct_consumers[ingredient.id] = consumers
        first_use[ingredient.id] = stage_index[consumers[0]] if consumers else len(operations)
    # Source order usually groups sauce, protein, and garnish ingredients. Keep
    # those groups together when independent operations share an X column.
    ingredients = display.inputs

    body_top = HEADER_TOP + 26 * len(display.headers)
    row_y: dict[str, int] = {}
    row_h: dict[str, int] = {}
    lane_labels: dict[str, str] = {}
    cursor_y = body_top
    for ingredient in ingredients:
        label = ingredient.label
        if not direct_consumers[ingredient.id]:
            label += " (not mapped)"
        lane_labels[ingredient.id] = label
        lines = textwrap.wrap(label, width=33) or [""]
        height = max(ROW_MIN_HEIGHT, 7 + 14 * len(lines))
        row_y[ingredient.id] = cursor_y
        row_h[ingredient.id] = height
        cursor_y += height

    input_names = {item.id: item.name for item in display.inputs}
    input_index = {ingredient.id: index for index, ingredient in enumerate(ingredients)}
    visible_details: dict[str, tuple[str, ...]] = {}
    for operation in operations:
        repeated = tuple(input_names[item] for item in operation.direct_ingredient_ids
                         if first_use[item] < stage_index[operation.id])
        visible_details[operation.id] = (
            (*operation.details, "+ " + ", ".join(repeated) + " again")
            if repeated else operation.details
        )
    stage_w = {operation.id: _operation_width(operation.label, visible_details[operation.id])
               for operation in operations}
    for operation in operations:
        row_indices = [input_index[item] for item in operation.ingredient_ids if item in input_index]
        first_row, last_row = min(row_indices), max(row_indices)
        required = _text_height(operation.label, visible_details[operation.id], stage_w[operation.id])
        available = sum(row_h[ingredients[index].id] for index in range(first_row, last_row + 1))
        if required > available:
            last_id = ingredients[last_row].id
            row_h[last_id] += required - available
    cursor_y = body_top
    for ingredient in ingredients:
        row_y[ingredient.id] = cursor_y
        cursor_y += row_h[ingredient.id]
    body_bottom = cursor_y

    stage_rank: dict[str, int] = {}
    spans: dict[str, tuple[int, int]] = {}
    predecessors: dict[str, list[str]] = {operation.id: [] for operation in operations}
    for link in display.links:
        predecessors[link.target].append(link.source)
    for operation in operations:
        row_indices = [input_index[item] for item in operation.ingredient_ids if item in input_index]
        spans[operation.id] = (min(row_indices), max(row_indices))
        stage_rank[operation.id] = max((stage_rank[source] + 1
                                        for source in predecessors[operation.id]), default=0)

    def place(floors: dict[str, int]) -> dict[str, int]:
        positions: dict[str, int] = {}
        for operation in operations:
            span = spans[operation.id]
            x = max(LEFT + LABEL_WIDTH, floors.get(operation.id, 0),
                    *(positions[source] + stage_w[source]
                      for source in predecessors[operation.id]))
            for previous in operations:
                if previous.id not in positions:
                    break
                other = spans[previous.id]
                if not (span[1] < other[0] or other[1] < span[0]):
                    x = max(x, positions[previous.id] + stage_w[previous.id])
            positions[operation.id] = x
        return positions

    floors: dict[str, int] = {}
    stage_x = place(floors)
    for _ in operations:
        aligned = floors.copy()
        for index, left in enumerate(operations):
            for right in operations[index + 1:]:
                a, b = left.id, right.id
                first, second = spans[a], spans[b]
                if (stage_rank[a] == stage_rank[b]
                        and (first[1] < second[0] or second[1] < first[0])
                        and abs(stage_x[a] - stage_x[b]) <= ALIGN_TOLERANCE):
                    boundary = max(stage_x[a], stage_x[b])
                    aligned[a] = max(aligned.get(a, 0), boundary)
                    aligned[b] = max(aligned.get(b, 0), boundary)
        updated = place(aligned)
        if updated == stage_x:
            break
        floors, stage_x = aligned, updated
    final_x = max((stage_x[operation.id] + stage_w[operation.id]
                   for operation in operations), default=LEFT + LABEL_WIDTH)

    lanes = tuple(IngredientLane(
        id=item.id, x=LEFT, y=row_y[item.id],
        width=stage_x[direct_consumers[item.id][0]] - LEFT
        if direct_consumers[item.id] else LABEL_WIDTH,
        height=row_h[item.id], label=lane_labels[item.id], row=index,
        first_operation=direct_consumers[item.id][0] if direct_consumers[item.id] else None,
    ) for index, item in enumerate(ingredients))

    regions: list[OperationRegion] = []
    for operation in operations:
        rows = [ingredient_id for ingredient_id in operation.ingredient_ids if ingredient_id in row_y]
        top = min(row_y[ingredient_id] for ingredient_id in rows)
        bottom = max(row_y[ingredient_id] + row_h[ingredient_id] for ingredient_id in rows)
        repeated = tuple(input_names[ingredient_id] for ingredient_id in operation.direct_ingredient_ids
                         if first_use[ingredient_id] < stage_index[operation.id])
        regions.append(OperationRegion(
            id=operation.id, x=stage_x[operation.id], y=top,
            width=stage_w[operation.id], height=bottom - top,
            label=operation.label, step_index=operation.step_index,
            details=operation.details, repeated_inputs=repeated,
        ))

    region_by_id = {region.id: region for region in regions}
    successors: dict[str, list[str]] = {operation.id: [] for operation in operations}
    for link in display.links:
        successors[link.source].append(link.target)

    def reaches(source: str, target: str) -> bool:
        pending = list(successors[source])
        seen: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current not in seen:
                seen.add(current)
                pending.extend(successors[current])
        return False

    # A direct semantic link can duplicate an existing path through another
    # visible operation. Only the latter needs a visual connection.
    visual_successors = {source: [target for target in targets
                                  if not any(other != target and reaches(other, target)
                                             for other in targets)]
                         for source, targets in successors.items()}
    continuations: list[Region] = []
    bridges: list[Region] = []
    for operation in operations:
        targets = visual_successors[operation.id]
        start_x = stage_x[operation.id] + stage_w[operation.id]
        region = region_by_id[operation.id]
        if len(targets) == 1:
            target_x = stage_x[targets[0]]
            blockers: list[Region] = [other for other in regions
                        if other.id not in (operation.id, targets[0])
                        and other.x < target_x and other.x + other.width > start_x
                        and other.y < region.y + region.height
                        and other.y + other.height > region.y]
            blockers.extend(lane for lane in lanes
                            if lane.x < target_x and lane.x + lane.width > start_x
                            and lane.y < region.y + region.height
                            and lane.y + lane.height > region.y)
            obstructed = bool(blockers)
            if target_x > start_x and not obstructed:
                region_by_id[operation.id] = OperationRegion(
                    id=region.id, x=region.x, y=region.y,
                    width=target_x - region.x, height=region.height,
                    label=region.label, step_index=region.step_index,
                    details=region.details, repeated_inputs=region.repeated_inputs,
                )
                continue
            if target_x > start_x and blockers:
                occupied = sorted((max(region.y, item.y),
                                   min(region.y + region.height, item.y + item.height))
                                  for item in blockers)
                free: list[tuple[int, int]] = []
                cursor = region.y
                for top, bottom in occupied:
                    if top > cursor:
                        free.append((cursor, top))
                    cursor = max(cursor, bottom)
                if cursor < region.y + region.height:
                    free.append((cursor, region.y + region.height))
                if free:
                    top, bottom = max(free, key=lambda interval: interval[1] - interval[0])
                    if bottom - top >= 12:
                        continuations.append(Region(
                            id=f"continuation_{operation.id}_{targets[0]}",
                            x=start_x, y=top, width=target_x - start_x,
                            height=bottom - top,
                        ))
                        continue
        for target in targets:
            next_x = stage_x[target]
            if next_x <= start_x:
                continue
            bridges.append(Region(
                id=f"bridge_{operation.id}_{target}", x=start_x,
                y=region.y + region.height // 2, width=next_x - start_x, height=2,
            ))
    regions = [region_by_id[operation.id] for operation in operations]

    globals_: list[Region] = []
    for index, header in enumerate(display.headers):
        following = [operation for operation in operations
                     if (operation.step_index or 0) >= (header.step_index or 0)]
        start_x = stage_x[header.stage_id] if header.stage_id else stage_x[following[0].id] if following else LEFT
        later_bake = next((operation for operation in following if "bake" in operation.source_label.casefold()
                           and operation.id != header.stage_id), None)
        end_x = max((stage_x[target] + stage_w[target] for target in header.target_ids),
                    default=stage_x[later_bake.id] + stage_w[later_bake.id] if later_bake else final_x)
        header_width = max(end_x - start_x,
                           min(len(header.label) * 5 + 12, final_x - start_x))
        header_x = start_x
        globals_.append(Region(
            id=header.id, x=header_x, y=HEADER_TOP + 26 * index,
            width=header_width, height=25, label=header.label,
        ))

    width = max([final_x,
                 *(region.x + region.width for region in globals_)]) + LEFT

    final_rows = [ingredient_id for ingredient_id in display.final_ingredient_ids if ingredient_id in row_y]
    final_top = min((row_y[ingredient_id] for ingredient_id in final_rows), default=body_top)
    final_bottom = max((row_y[ingredient_id] + row_h[ingredient_id] for ingredient_id in final_rows),
                       default=body_bottom)
    final = Region(
        id=display.final_id, x=final_x, y=final_top,
        width=0, height=final_bottom - final_top, label=display.final_label,
    )
    title = display.final_label[7:] if display.final_label.casefold().startswith("served ") else display.final_label
    return TRNLayout(
        width=width, height=body_bottom + 24, title=title.title(),
        ingredients=lanes, operations=tuple(regions),
        continuations=tuple(continuations), bridges=tuple(bridges),
        global_operations=tuple(globals_), final=final,
    )
