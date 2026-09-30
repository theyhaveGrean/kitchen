"""Collapse semantic material nodes into the operations shown by a TRN chart."""

from __future__ import annotations

import heapq
import re
from collections import defaultdict
from dataclasses import dataclass

from .graph import GraphNode, RecipeGraph


@dataclass(frozen=True)
class DisplayInput:
    id: str
    label: str
    name: str
    consumers: tuple[str, ...]


@dataclass(frozen=True)
class DisplayOperation:
    id: str
    label: str
    source_label: str
    step_index: int | None
    details: tuple[str, ...]
    ingredient_ids: frozenset[str]
    direct_ingredient_ids: tuple[str, ...]


@dataclass(frozen=True)
class DisplayLink:
    source: str
    target: str
    via_intermediates: tuple[str, ...]


@dataclass(frozen=True)
class DisplayHeader:
    id: str
    label: str
    step_index: int | None
    stage_id: str | None
    target_ids: tuple[str, ...]


@dataclass(frozen=True)
class TRNDisplayGraph:
    inputs: tuple[DisplayInput, ...]
    operations: tuple[DisplayOperation, ...]
    links: tuple[DisplayLink, ...]
    headers: tuple[DisplayHeader, ...]
    final_id: str
    final_label: str
    final_ingredient_ids: frozenset[str]


def _topological_ids(graph: RecipeGraph) -> list[str]:
    order = {node.id: index for index, node in enumerate(graph.nodes)}
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {node.id: 0 for node in graph.nodes}
    for edge in graph.edges:
        if edge.source not in indegree or edge.target not in indegree:
            raise ValueError("Cannot display an edge with a missing node")
        if edge.target not in outgoing[edge.source]:
            outgoing[edge.source].add(edge.target)
            indegree[edge.target] += 1
    ready = [order[node_id] for node_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    result: list[str] = []
    while ready:
        node_id = graph.nodes[heapq.heappop(ready)].id
        result.append(node_id)
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, order[target])
    if len(result) != len(graph.nodes):
        raise ValueError("Cannot display a cyclic graph")
    return result


def _operation_order(graph: RecipeGraph, ancestry: dict[str, set[str]]) -> list[GraphNode]:
    nodes = {node.id: node for node in graph.nodes}
    operations = [node for node in graph.nodes if node.type == "operation" and ancestry[node.id]]
    operation_ids = {node.id for node in operations}
    original = {node.id: index for index, node in enumerate(graph.nodes)}
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree = {node.id: 0 for node in operations}
    for source in operations:
        pending = [edge.target for edge in graph.edges if edge.source == source.id]
        seen: set[str] = set()
        while pending:
            target = pending.pop()
            if target in seen:
                continue
            seen.add(target)
            if target in operation_ids:
                if target != source.id and target not in outgoing[source.id]:
                    outgoing[source.id].add(target)
                    indegree[target] += 1
            elif nodes[target].type == "intermediate":
                pending.extend(edge.target for edge in graph.edges if edge.source == target)
    ready = [(nodes[node_id].step_index or 0, original[node_id], node_id)
             for node_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[GraphNode] = []
    while ready:
        _, _, node_id = heapq.heappop(ready)
        ordered.append(nodes[node_id])
        for target in outgoing[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, (nodes[target].step_index or 0, original[target], target))
    if len(ordered) != len(operations):
        raise ValueError("Cannot order recipe operations")
    return ordered


def _ingredient_label(node: GraphNode) -> str:
    amount = " ".join(part for part in (node.quantity, node.unit) if part)
    preparation = f", {node.preparation}" if node.preparation else ""
    return f"{amount} {node.label}{preparation}".strip()


def _operation_details(node: GraphNode) -> tuple[str, ...]:
    return tuple(value for value in (node.temperature, node.duration, node.heat_level)
                 if value and value.casefold() not in node.label.casefold())


def _split_preheat(node: GraphNode) -> tuple[str, str] | None:
    match = re.match(r"(?i)^preheat(?: the)? (oven|broiler) and (.+)$", node.label)
    if match:
        return f"Preheat {match.group(1)}", match.group(2).capitalize()
    return None


def _display_action(node: GraphNode) -> str:
    split = _split_preheat(node)
    if split:
        return split[1]
    label = node.label.strip()
    for pattern, action in (
        (r"(?i)^whisk\b", "Whisk"),
        (r"(?i)^marinate\b", "Marinate"),
        (r"(?i)^broil\b", "Broil"),
        (r"(?i)^toast .*spices\b", "Toast spices"),
        (r"(?i)^simmer\b", "Simmer"),
        (r"(?i)^garnish and serve$", "Garnish + serve"),
    ):
        if re.search(pattern, label):
            return action
    return label


def build_trn_display_graph(graph: RecipeGraph) -> TRNDisplayGraph:
    """Keep ingredients and operations; replace product chains with operation links."""
    nodes = {node.id: node for node in graph.nodes}
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        incoming[edge.target].append(edge.source)
        outgoing[edge.source].append(edge.target)
    ancestry: dict[str, set[str]] = {}
    for node_id in _topological_ids(graph):
        ancestors = {node_id} if nodes[node_id].type == "ingredient" else set()
        for source in incoming[node_id]:
            ancestors.update(ancestry[source])
        ancestry[node_id] = ancestors

    ordered = _operation_order(graph, ancestry)
    displayed_ids = {node.id for node in ordered}
    inputs = tuple(DisplayInput(
        id=node.id, label=_ingredient_label(node), name=node.label,
        consumers=tuple(target for target in outgoing[node.id] if target in displayed_ids),
    ) for node in graph.nodes if node.type == "ingredient")
    operations = tuple(DisplayOperation(
        id=node.id, label=_display_action(node), source_label=node.label,
        step_index=node.step_index, details=() if _split_preheat(node) else _operation_details(node),
        ingredient_ids=frozenset(ancestry[node.id]),
        direct_ingredient_ids=tuple(source for source in incoming[node.id]
                                    if nodes[source].type == "ingredient"),
    ) for node in ordered)

    links: list[DisplayLink] = []
    for operation in ordered:
        pending: list[tuple[str, tuple[str, ...]]] = [(target, ()) for target in outgoing[operation.id]]
        seen: set[str] = set()
        while pending:
            target, via = pending.pop()
            if target in seen:
                continue
            seen.add(target)
            if target in displayed_ids:
                links.append(DisplayLink(operation.id, target, via))
            elif nodes[target].type == "intermediate":
                pending.extend((next_id, (*via, target)) for next_id in outgoing[target])

    original = {node.id: index for index, node in enumerate(graph.nodes)}
    header_nodes = [node for node in graph.nodes if node.type == "operation"
                    and (not ancestry[node.id] or _split_preheat(node))]
    header_nodes.sort(key=lambda node: (node.step_index or 0, original[node.id]))
    headers = tuple(DisplayHeader(
        id=node.id,
        label=" ".join(((_split_preheat(node) or (node.label, ""))[0]
                        if node.id in displayed_ids else node.label, *_operation_details(node))),
        step_index=node.step_index,
        stage_id=node.id if node.id in displayed_ids else None,
        target_ids=tuple(target for target in outgoing[node.id] if target in displayed_ids),
    ) for node in header_nodes)
    final_node = next((node for node in graph.nodes if node.type == "final"), None)
    final_id = final_node.id if final_node else "final"
    return TRNDisplayGraph(
        inputs=inputs, operations=operations, links=tuple(links), headers=headers,
        final_id=final_id, final_label=final_node.label if final_node else "Finished dish",
        final_ingredient_ids=frozenset(ancestry.get(final_id, ())),
    )
