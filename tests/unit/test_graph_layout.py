"""TRN geometry stays deterministic and separate from recipe semantics."""

from recipe_scraper.graph import GraphEdge, GraphNode, RecipeGraph
from recipe_scraper.graph_display import build_trn_display_graph
from recipe_scraper.graph_layout import build_trn_layout
from recipe_scraper.graph_render import render_svg


def node(node_id: str, kind: str, label: str, step: int | None = None) -> GraphNode:
    return GraphNode.model_validate({
        "id": node_id, "type": kind, "label": label,
        "ingredient_id": node_id if kind == "ingredient" else None,
        "quantity": "1" if kind == "ingredient" else None,
        "unit": None, "preparation": None, "original_text": None,
        "step_index": step, "source_instruction": None,
        "temperature": None, "duration": None, "heat_level": None,
    })


def branch_graph() -> RecipeGraph:
    names = [
        ("sausage", "ingredient", "sausage", None),
        ("tomato", "ingredient", "tomato", None),
        ("ziti", "ingredient", "ziti", None),
        ("ricotta", "ingredient", "ricotta", None),
        ("brown", "operation", "Brown sausage", 1),
        ("browned", "intermediate", "browned sausage", None),
        ("simmer", "operation", "Simmer sauce", 2),
        ("sauce", "intermediate", "red sauce", None),
        ("boil", "operation", "Boil ziti", 3),
        ("drained", "intermediate", "drained ziti", None),
        ("mix", "operation", "Mix ricotta", 4),
        ("filling", "intermediate", "ricotta mixture", None),
        ("preheat", "operation", "Preheat oven", 4),
        ("combine", "operation", "Combine layers", 5),
        ("assembled", "intermediate", "assembled ziti", None),
        ("bake", "operation", "Bake", 6),
        ("final", "final", "baked ziti", None),
    ]
    pairs = [
        ("sausage", "brown"), ("brown", "browned"),
        ("browned", "simmer"), ("tomato", "simmer"), ("simmer", "sauce"),
        ("ziti", "boil"), ("boil", "drained"),
        ("ricotta", "mix"), ("mix", "filling"),
        ("sauce", "combine"), ("drained", "combine"), ("filling", "combine"),
        ("combine", "assembled"), ("assembled", "bake"),
        ("preheat", "bake"), ("bake", "final"),
    ]
    kinds = {item[0]: item[1] for item in names}
    edges = [GraphEdge(
        source=source, target=target,
        type="dependency" if source == "preheat" else
        "output" if kinds[source] == "operation" else "input",
    ) for source, target in pairs]
    return RecipeGraph(nodes=[node(*item) for item in names], edges=edges,
                       unresolved_references=[], warnings=[])


def test_trn_layout_uses_ingredient_rows_and_rectangular_merges() -> None:
    graph = branch_graph()
    display = build_trn_display_graph(graph)
    layout = build_trn_layout(display)
    lanes = {item.id: item for item in layout.ingredients}
    stages = {item.id: item for item in layout.operations}
    assert [item.id for item in layout.ingredients] == ["sausage", "tomato", "ziti", "ricotta"]
    assert lanes["sausage"].x + lanes["sausage"].width == stages["brown"].x
    assert lanes["ziti"].x + lanes["ziti"].width == stages["boil"].x
    assert lanes["ricotta"].x + lanes["ricotta"].width == stages["mix"].x
    assert stages["simmer"].y < stages["boil"].y < stages["mix"].y
    assert stages["brown"].x == stages["boil"].x == stages["mix"].x
    assert stages["brown"].x + stages["brown"].width == stages["simmer"].x
    assert stages["simmer"].x + stages["simmer"].width == stages["combine"].x
    assert stages["boil"].x + stages["boil"].width == stages["combine"].x
    assert stages["mix"].x + stages["mix"].width == stages["combine"].x
    assert not layout.continuations and not layout.bridges
    assert stages["combine"].y == lanes["sausage"].y
    assert stages["combine"].y + stages["combine"].height == lanes["ricotta"].y + lanes["ricotta"].height
    assert all(not region.label for region in layout.continuations)
    assert {item.id for item in display.operations}.isdisjoint({"browned", "sauce", "drained", "filling"})
    assert any(link.source == "simmer" and link.target == "combine"
               and link.via_intermediates == ("sauce",) for link in display.links)
    assert [region.id for region in layout.global_operations] == ["preheat"]
    assert layout.global_operations[0].x < stages["bake"].x
    assert layout.width < 900
    assert layout.final.width < 112
    svg = render_svg(graph)
    assert "<path" not in svg and "<marker" not in svg
    assert "red sauce" not in svg and "Preheat oven" in svg


def test_chicken_tikka_branches_pack_without_blank_cells() -> None:
    names = [
        ("spice", "ingredient", "spice", None),
        ("chicken", "ingredient", "chicken", None),
        ("onion", "ingredient", "onion", None),
        ("tomato", "ingredient", "tomato", None),
        ("whisk", "operation", "Whisk", 1),
        ("marinade", "intermediate", "marinade", None),
        ("marinate", "operation", "Marinate", 2),
        ("marinated", "intermediate", "marinated chicken", None),
        ("broil", "operation", "Broil", 3),
        ("broiled", "intermediate", "broiled chicken", None),
        ("cook", "operation", "Cook onion and ginger", 4),
        ("cooked", "intermediate", "cooked onion", None),
        ("toast", "operation", "Toast spices", 5),
        ("toasted", "intermediate", "toasted spices", None),
        ("sauce", "operation", "Simmer", 6),
        ("simmered", "intermediate", "sauce", None),
        ("merge", "operation", "Simmer together", 7),
        ("final", "final", "chicken dinner", None),
    ]
    pairs = [
        ("spice", "whisk"), ("whisk", "marinade"),
        ("marinade", "marinate"), ("chicken", "marinate"),
        ("marinate", "marinated"), ("marinated", "broil"),
        ("broil", "broiled"), ("broiled", "merge"),
        ("onion", "cook"), ("cook", "cooked"),
        ("cooked", "toast"), ("toast", "toasted"),
        ("toasted", "sauce"), ("tomato", "sauce"),
        ("sauce", "simmered"), ("simmered", "merge"),
        ("merge", "final"),
    ]
    kinds = {item[0]: item[1] for item in names}
    graph = RecipeGraph(
        nodes=[node(*item) for item in names],
        edges=[GraphEdge(source=source, target=target,
                         type="output" if kinds[source] == "operation" else "input")
               for source, target in pairs],
        unresolved_references=[], warnings=[],
    )
    layout = build_trn_layout(build_trn_display_graph(graph))
    stages = {item.id: item for item in layout.operations}
    for source, target in (("whisk", "marinate"), ("marinate", "broil"),
                           ("cook", "toast"), ("toast", "sauce"),
                           ("broil", "merge"), ("sauce", "merge")):
        assert stages[source].x + stages[source].width == stages[target].x
    assert stages["marinate"].x == stages["toast"].x
    assert stages["whisk"].x + stages["whisk"].width == stages["cook"].x + stages["cook"].width
    assert not layout.continuations and not layout.bridges


def test_overlapping_side_branch_uses_unbordered_material_continuation() -> None:
    names = [
        ("a", "ingredient", "a", None),
        ("b", "ingredient", "b", None),
        ("c", "ingredient", "c", None),
        ("upper", "operation", "Whisk", 1),
        ("upper_product", "intermediate", "upper mixture", None),
        ("lower", "operation", "Prepare pan", 2),
        ("lower_product", "intermediate", "prepared pan", None),
        ("merge", "operation", "Combine", 3),
        ("final", "final", "finished dish", None),
    ]
    pairs = [
        ("a", "upper"), ("b", "upper"),
        ("upper", "upper_product"), ("upper_product", "merge"),
        ("b", "lower"), ("c", "lower"),
        ("lower", "lower_product"), ("lower_product", "merge"),
        ("merge", "final"),
    ]
    kinds = {item[0]: item[1] for item in names}
    graph = RecipeGraph(
        nodes=[node(*item) for item in names],
        edges=[GraphEdge(source=source, target=target,
                         type="output" if kinds[source] == "operation" else "input")
               for source, target in pairs],
        unresolved_references=[], warnings=[],
    )
    layout = build_trn_layout(build_trn_display_graph(graph))
    assert [item.id for item in layout.continuations] == ["continuation_upper_merge"]
    assert not layout.bridges
    upper = next(item for item in layout.operations if item.id == "upper")
    merge = next(item for item in layout.operations if item.id == "merge")
    continuation = layout.continuations[0]
    assert upper.x + upper.width == continuation.x
    assert continuation.x + continuation.width == merge.x
    assert continuation.height < upper.height


def test_reused_ingredient_is_shown_at_later_stage() -> None:
    graph = branch_graph()
    graph.edges.append(GraphEdge(source="tomato", target="combine", type="input"))
    layout = build_trn_layout(build_trn_display_graph(graph))
    stages = {item.id: item for item in layout.operations}
    assert stages["combine"].repeated_inputs == ("tomato",)
    assert "again" in render_svg(graph)


def test_multiple_global_operations_get_separate_bands() -> None:
    graph = branch_graph()
    graph.nodes.append(node("warm_pan", "operation", "Warm pan", 1))
    graph.edges.append(GraphEdge(source="warm_pan", target="brown", type="dependency"))
    layout = build_trn_layout(build_trn_display_graph(graph))
    assert len(layout.global_operations) == 2
    assert len({region.y for region in layout.global_operations}) == 2
    assert min(lane.y for lane in layout.ingredients) > max(region.y + region.height for region in layout.global_operations)


def test_unmapped_ingredient_does_not_flow_into_final() -> None:
    graph = branch_graph()
    graph.nodes.append(node("parsley", "ingredient", "parsley"))
    layout = build_trn_layout(build_trn_display_graph(graph))
    lane = next(item for item in layout.ingredients if item.id == "parsley")
    assert lane.first_operation is None
    assert lane.width < layout.final.x - lane.x
    assert "not mapped" in lane.label


def test_preheat_and_prepare_pan_uses_header_and_process_stage() -> None:
    graph = branch_graph()
    preheat = next(item for item in graph.nodes if item.id == "preheat")
    preheat.label = "Preheat oven and prepare pan"
    graph.nodes.extend((node("oil", "ingredient", "oil"), node("pan", "intermediate", "prepared pan")))
    graph.edges.extend((
        GraphEdge(source="oil", target="preheat", type="input"),
        GraphEdge(source="preheat", target="pan", type="output"),
        GraphEdge(source="pan", target="bake", type="input"),
    ))
    layout = build_trn_layout(build_trn_display_graph(graph))
    stage = next(item for item in layout.operations if item.id == "preheat")
    lane = next(item for item in layout.ingredients if item.id == "oil")
    assert stage.label == "Prepare pan"
    assert lane.x + lane.width == stage.x
    assert any(region.label.startswith("Preheat oven") for region in layout.global_operations)


def test_short_cooking_actions_make_narrow_columns() -> None:
    graph = branch_graph()
    for item in graph.nodes:
        if item.id == "brown":
            item.label = "Whisk marinade ingredients"
        elif item.id == "simmer":
            item.label = "Marinate chicken"
        elif item.id == "boil":
            item.label = "Broil chicken"
    display = build_trn_display_graph(graph)
    layout = build_trn_layout(display)
    stages = {item.id: item for item in layout.operations}
    assert [stages[item].label for item in ("brown", "simmer", "boil")] == ["Whisk", "Marinate", "Broil"]
    assert all(stages[item].width <= 70 for item in ("brown", "simmer"))


def test_ingredient_row_height_follows_wrapped_label() -> None:
    graph = branch_graph()
    next(item for item in graph.nodes if item.id == "ricotta").label = (
        "whole milk ricotta cheese with a very long preparation note"
    )
    layout = build_trn_layout(build_trn_display_graph(graph))
    lanes = {item.id: item for item in layout.ingredients}
    assert lanes["ricotta"].height > lanes["ziti"].height
    assert lanes["tomato"].height <= 24
