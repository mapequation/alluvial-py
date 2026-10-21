"""Worked examples from docs/dev/port-notes (model.md §10, layout.md §10, streamlines.md §10, colors-render.md §4
and §6), all verified against the TS engine. They pin behaviour the fixture suite does not check directly:
similarity values, duplicate-identifier quirks and the colouring quirks."""

from __future__ import annotations

import pytest

from alluvial._palette import C3_SINEBOW
from alluvial.engine import RIGHT, Diagram, DiagramStore
from alluvial.io.types import NetworkFile, Node
from alluvial.layout import LayoutOptions


def net(network_id: str, rows: list[tuple]) -> NetworkFile:
    """Rows are ``(identifier, path, flow)`` or ``(identifier, path, flow, node_id)``; node id defaults to int(identifier)."""
    nodes = []
    for row in rows:
        identifier, path, flow = row[:3]
        node_id = row[3] if len(row) > 3 else int(identifier)
        nodes.append(Node(id=node_id, flow=flow, path=path, name=str(identifier), identifier=str(identifier)))
    return NetworkFile(id=network_id, name=network_id, format="tree", nodes=nodes)


def branches(
    diagram: Diagram, network_id: str, module_id: str
) -> list[tuple[str, list[tuple[str, list[str]]]]]:
    module = diagram.get_network(network_id).get_module(module_id)
    return [
        (
            group.id,
            [
                (sn.current_id, [leaf.identifier for leaf in sn.children])
                for b in group.children
                for sn in b.children
            ],
        )
        for group in module.children
    ]


def sl(diagram: Diagram, network_id: str, module_id: str, side: int) -> list[tuple[str, list[str]]]:
    module = diagram.get_network(network_id).get_module(module_id)
    return [
        (sn.current_id, [leaf.identifier for leaf in sn.children])
        for group in module.children
        for sn in (group.left if side < 0 else group.right).children
    ]


A_102 = [("1", "1:1", 0.1), ("2", "1:2", 0.2), ("3", "1:3", 0.3), ("4", "1:4", 0.15), ("5", "2:1", 0.25)]
B_102 = [("1", "1:1", 0.1), ("2", "2:1", 0.2), ("3", "3:1", 0.3), ("4", "2:2", 0.15), ("6", "3:2", 0.25)]


def test_debug5_structure() -> None:
    """model.md §10.1."""
    a = [
        ("1", "1:1:1", 0.2),
        ("82", "1:1:2", 0.2),
        ("144", "1:2:3", 0.2),
        ("171", "2:1:1", 0.2),
        ("179", "2:2:2", 0.2),
    ]
    b = [
        ("1", "1:1:1", 0.2),
        ("82", "1:2:1", 0.2),
        ("144", "2:1:1", 0.2),
        ("171", "2:1:2", 0.2),
        ("179", "2:2:3", 0.2),
    ]
    d = Diagram([net("A", a), net("B", b)])
    d.calc_flow()
    assert d.get_network("A").get_module("1").flow == 0.6000000000000001
    assert sl(d, "A", "1", RIGHT) == [
        ("A_module1_group-1_right--B_module1_group-1_left", ["1", "82"]),
        ("A_module1_group-1_right--B_module2_group-1_left", ["144"]),
    ]
    assert sl(d, "B", "2", -1) == [
        ("B_module2_group-1_left--A_module1_group-1_right", ["144"]),
        ("B_module2_group-1_left--A_module2_group-1_right", ["171", "179"]),
    ]
    assert sl(d, "B", "2", RIGHT) == [("B_module2_group-1_right", ["144", "171", "179"])]


def test_swap_remove_order_and_update_reshuffle() -> None:
    """model.md §10.2 and §10.3, including the getSimilarModules values."""
    d = Diagram([net("A", A_102), net("B", B_102)])
    d.calc_flow()
    a1 = d.get_network("A").get_module("1")
    assert a1.flow == 0.7500000000000001
    assert sl(d, "A", "1", RIGHT) == [
        ("A_module1_group-1_right--B_module3_group-1_left", ["3"]),
        ("A_module1_group-1_right--B_module1_group-1_left", ["1"]),
        ("A_module1_group-1_right--B_module2_group-1_left", ["2", "4"]),
    ]
    assert sl(d, "B", "3", -1) == [
        ("B_module3_group-1_left--A_module1_group-1_right", ["3"]),
        ("B_module3_group-1_left", ["6"]),
    ]

    leaf = d.get_network("A").get_leaf_node("2")
    leaf.highlight_index = 0
    leaf.update()
    d.calc_flow()
    assert a1.flow == 0.75
    assert [(g.id, g.flow) for g in a1.children] == [("A_module1_group-1", 0.55), ("A_module1_group0", 0.2)]
    assert [[x.identifier for x in sn.children] for sn in a1.children[0].left.children] == [["1", "4", "3"]]
    assert sl(d, "B", "2", -1) == [
        ("B_module2_group-1_left--A_module1_group-1_right", ["4"]),
        ("B_module2_group-1_left--A_module1_group0_right", ["2"]),
    ]

    a1.set_color(1)
    assert [g.id for g in a1.children] == ["A_module1_group1"]
    assert [x.identifier for x in a1.children[0].left.children[0].children] == ["1", "4", "3", "2"]
    assert sl(d, "A", "1", RIGHT) == [
        ("A_module1_group1_right--B_module1_group-1_left", ["1"]),
        ("A_module1_group1_right--B_module2_group-1_left", ["4", "2"]),
        ("A_module1_group1_right--B_module3_group-1_left", ["3"]),
    ]
    assert sl(d, "B", "3", -1) == [
        ("B_module3_group-1_left", ["6"]),
        ("B_module3_group-1_left--A_module1_group1_right", ["3"]),
    ]
    similar = [(m.module.id, m.similarity) for m in a1.get_similar_modules(RIGHT)]
    expected = [
        ("B_module2", 0.6617550740496512),
        ("B_module3", 0.4646241078641882),
        ("B_module1", 0.2961169789042666),
    ]
    assert [s[0] for s in similar] == [e[0] for e in expected]
    for (_, got), (_, want) in zip(similar, expected):
        assert got == pytest.approx(want, abs=1e-14)


def test_duplicate_identifiers_link_only_the_registered_leaf() -> None:
    """E6: only mutually registered leaves link; other duplicates stay dangling, no steal and no ``NULL--`` id."""
    d = Diagram(
        [
            net("A", [("x", "1:1", 0.5, 1), ("y", "2:1", 0.5, 2)]),
            net("B", [("x", "1:1", 0.3, 1), ("x", "2:1", 0.3, 2), ("y", "2:2", 0.4, 3)]),
        ]
    )
    assert sl(d, "B", "1", -1) == [("B_module1_group-1_left", ["x"])]
    assert sl(d, "A", "1", RIGHT) == [("A_module1_group-1_right--B_module2_group-1_left", ["x"])]

    d = Diagram(
        [
            net("A", [("x", "1:1", 0.5, 1), ("y", "1:2", 0.5, 2)]),
            net("B", [("x", "1:1", 0.3, 1), ("y", "1:2", 0.3, 2), ("y", "2:1", 0.4, 3)]),
        ]
    )
    expected = [
        ("A_module1_group-1_right--B_module1_group-1_left", ["x"]),
        ("A_module1_group-1_right--B_module2_group-1_left", ["y"]),
    ]
    assert sl(d, "A", "1", RIGHT) == expected
    # A later update() of any leaf (the old re-steal path) leaves the graph unchanged.
    for network in d.children:
        for leaf in network.built_leaf_nodes:
            leaf.update()
    assert sl(d, "A", "1", RIGHT) == expected
    b_left = d.get_network("B").get_module("1").children[0].left.children
    assert [(sn.current_id, [x.identifier for x in sn.children]) for sn in b_left] == [
        ("B_module1_group-1_left--A_module1_group-1_right", ["x"]),
        ("B_module1_group-1_left", ["y"]),
    ]
    assert [sn.link is not None for sn in b_left] == [True, False]


LAYOUT_OPTS = {
    "height": 100,
    "module_width": 10,
    "streamline_fraction": 2,
    "flow_threshold": 0,
    "margin_exponent": 2,
}


def _layout(networks: list[NetworkFile], **kwargs) -> Diagram:
    d = Diagram(networks)
    d.calc_flow()
    d.update_layout(LayoutOptions(**{**LAYOUT_OPTS, **kwargs}))
    return d


def test_layout_example_1() -> None:
    """layout.md §10.1."""
    a = net("A", [("1", "1:1", 0.3), ("2", "2:1", 0.2), ("3", "1:2", 0.1), ("4", "3:1", 0.4)])
    b = net("B", [("1", "2:1", 0.25), ("2", "1:1", 0.25), ("3", "1:2", 0.1), ("5", "1:3", 0.1)])
    d = _layout([a, b])
    na, nb = d.children
    assert (d.width, na.flow, nb.flow) == (40, 1, 0.7)
    assert (na.flow_threshold, nb.flow_threshold) == (0.2, 0.25)
    assert [m.module_id for m in na.children] == ["1", "3", "2"]
    assert [m.module_id for m in nb.children] == ["1", "2"]
    m1, m3, m2 = na.children
    assert (m1.y, m1.height, m1.margin) == (63.2, 36.800000000000004, 4)
    assert m1.children[0].left.y == 63.199999999999996
    assert [(sn.y, sn.height) for sn in m1.children[0].right.children] == [
        (90.8, 9.200000000000001),
        (63.2, 27.599999999999998),
    ]
    assert (m3.y, m2.y, m2.height, m2.margin) == (22.4, -3.552713678800501e-15, 18.400000000000002, 0)
    assert m1.name_position == (-20, 81.60000000000001) and m1.text_anchor == "end"
    b1, b2 = nb.children
    assert b1.flow == 0.44999999999999996
    assert [(sn.y, sn.height) for sn in b1.children[0].left.children] == [
        (90.8, 9.200000000000001),
        (81.6, 9.200000000000001),
        (58.599999999999994, 23),
    ]
    assert (b2.y, b2.height) == (31.6, 23)
    assert [b1.name_position, b2.name_position] == [(60, 79.3), (60, 43.1)]
    assert [na.name_position, nb.name_position] == [(5, 120), (35, 120)]

    d = _layout([a, b], vertical_align="justify")
    b1, b2 = d.children[1].children
    assert b1.margin == 35.60000000000001
    assert (b2.y, b2.height) == (-7.105427357601002e-15, 23)


def test_layout_example_2_cap_invisible_groups() -> None:
    """layout.md §10.2."""
    a_rows = [
        ("1", "1:1", 0.3),
        ("2", "2:1", 0.2),
        ("3", "1:2", 0.1),
        ("4", "3:1", 0.4),
        ("6", "4:1", 0.05),
        ("8", "1;3;", 0.05),
    ]
    b = net(
        "B",
        [
            ("1", "2:1", 0.25),
            ("2", "1:1", 0.25),
            ("3", "1:2", 0.1),
            ("5", "1:3", 0.1),
            ("6", "1:4", 0.05),
            ("8", "2:2", 0.05),
        ],
    )

    def a() -> NetworkFile:
        f = net("A", a_rows)
        f.nodes[0].highlight_index = 0
        return f

    d = _layout([a(), b], margin_exponent=4, flow_threshold=0.06)
    na, nb = d.children
    assert (na.flow, nb.flow) == (1.1, 0.7999999999999999)
    assert [m.module_id for m in na.children] == ["1", "3", "2", "4"]
    m1 = na.children[0]
    assert (m1.y, m1.height, m1.margin) == (67.27272727272727, 32.72727272727273, 10)
    assert [(g.highlight_index, g.insignificant, g.y) for g in m1.children] == [
        (-1, False, 92.72727272727272),
        (0, False, 70.9090909090909),
        (-1, True, 67.27272727272727),
    ]
    assert (na.children[3].x, na.children[3].height, na.children[3].index) == (0, 0, 3)
    assert [(sn.y, sn.height) for sn in nb.children[0].children[0].left.children] == [
        (92.72727272727272, 7.272727272727273),
        (89.09090909090908, 3.6363636363636367),
        (81.81818181818181, 7.272727272727273),
        (63.63636363636363, 18.18181818181818),
    ]

    d = _layout([a(), b], margin_exponent=4, flow_threshold=0.06, sort_modules_by="highlight_index")
    assert [m.module_id for m in d.children[0].children] == ["2", "3", "1", "4"]
    assert d.children[0].children[0].y == 85.45454545454545
    d = _layout([a(), b], margin_exponent=4, flow_threshold=0.06, sort_modules_by="node_id")
    assert [m.module_id for m in d.children[1].children] == ["2", "1"]
    assert d.children[1].children[0].y == 78.18181818181817
    d = _layout([a(), b], margin_exponent=4, flow_threshold=0.06, module_size="nodes")
    assert (d.children[0].children[0].y, d.children[0].children[0].height) == (60.000000000000014, 40)


def test_streamline_mini_fixture_links() -> None:
    """streamlines.md §10 (name identifiers, three networks)."""

    def named(network_id: str, rows: list[tuple[str, str, float]]) -> NetworkFile:
        return net(network_id, [(i, p, f, k) for k, (i, p, f) in enumerate(rows)])

    a = named(
        "A", [("a", "1:1", 0.3), ("b", "1:2", 0.2), ("c", "2:1", 0.25), ("d", "2:2", 0.15), ("e", "3:1", 0.1)]
    )
    b = named("B", [("c", "1:1", 0.35), ("a", "1:2", 0.3), ("b", "2:1", 0.2), ("f", "2:2", 0.15)])
    c = named("C", [("a", "1:1", 0.6), ("f", "1:2", 0.4)])
    d = Diagram([a, b, c])
    d.calc_flow()
    d.update_layout(LayoutOptions(flow_threshold=0))
    links = [(link.id, link.avg_height, link.path) for link in d.children[0].get_links(0)]
    assert links == [
        (
            "A_module1_group-1_right--B_module1_group-1_left",
            170.4,
            "M80,600C160,600,160,600,240,600L240,429.6C160,429.6,160,429.6,80,429.6Z",
        ),
        (
            "A_module2_group-1_right--B_module1_group-1_left",
            170.39999999999998,
            (
                "M80,214.8C160,214.8,160,429.6,240,429.6L240,230.80000000000004C160,230.80000000000004,160,"
                "72.80000000000001,80,72.80000000000001Z"
            ),
        ),
        (
            "A_module1_group-1_right--B_module2_group-1_left",
            113.60000000000001,
            (
                "M80,429.6C160,429.6,160,129.60000000000002,240,129.60000000000002L240,16.000000000000014C160,"
                "16.000000000000014,160,316,80,316Z"
            ),
        ),
    ]
    assert [link.path for link in d.children[1].get_links(0)] == [
        (
            "M320,401.20000000000005C400,401.20000000000005,400,600,480,600L480,259.2C400,259.2,400,230.80000000000004,"
            "320,230.80000000000004Z"
        ),
        "M320,101.2C400,101.2,400,259.2,480,259.2L480,31.99999999999997C400,31.99999999999997,400,16,320,16Z",
    ]


def _store(networks: list[NetworkFile]) -> DiagramStore:
    store = DiagramStore(LayoutOptions(flow_threshold=0))
    store.set_networks(networks)
    return store


def _module_indices(store: DiagramStore) -> list[dict[str, int]]:
    return [{m.module_id: m.highlight_index for m in n.children} for n in store.diagram.children]


def test_color_single_network_colours_every_module() -> None:
    """E4: recolouring keeps single-leaf modules in place, so the single-network walk colours every module."""
    f = net(
        "A",
        [
            ("1", "1:1", 0.3),
            ("2", "1:2", 0.3),
            ("3", "3:1", 0.2),
            ("4", "3:2", 0.1),
            ("5", "2:1", 0.06),
            ("6", "4:1", 0.04),
        ],
    )
    store = _store([f])
    assert [m.module_id for m in store.diagram.children[0].children] == ["1", "3", "2", "4"]
    modules = list(store.diagram.children[0].children)
    store.color_matching_modules_in_all_networks()
    assert _module_indices(store) == [{"1": 0, "3": 1, "2": 2, "4": 3}]
    assert store.diagram.children[0].children == modules  # same objects, same order
    assert store.highlight_colors == list(C3_SINEBOW[:4])


def test_color_matching_counter_shared_by_all_pairs() -> None:
    """colors-render.md §6.1 (S1, fix round WP6): one colour counter for all network pairs, so the chain b.2 -> c.1
    that starts in network 1 gets scheme[1] (before: all five modules got index 0)."""
    a = net("a", [("1", "1:1", 0.5), ("2", "1:2", 0.5)])
    b = net("b", [("1", "1:1", 0.25), ("2", "1:2", 0.25), ("3", "2:1", 0.25), ("4", "2:2", 0.25)])
    c = net("c", [("3", "1:1", 0.25), ("4", "1:2", 0.25), ("1", "2:1", 0.25), ("2", "2:2", 0.25)])
    store = _store([a, b, c])
    store.color_matching_modules_in_all_networks()
    assert _module_indices(store) == [{"1": 0}, {"1": 0, "2": 1}, {"1": 1, "2": 0}]
    assert store.highlight_colors == [C3_SINEBOW[0], C3_SINEBOW[1]]


def _colored(network_id: str, colors, nodes: list[dict]) -> NetworkFile:
    f = net(network_id, [(str(i + 1), f"{i + 1}:1", 1 / len(nodes)) for i in range(len(nodes))])
    f.colors = colors
    for node, attrs in zip(f.nodes, nodes, strict=True):
        for k, v in attrs.items():
            setattr(node, k, v)
    return f


def _mixed_palette_files() -> list[NetworkFile]:
    return [
        _colored(
            "a", ["red", "blue"], [{"highlight_index": 1}, {"highlight_index": 0}, {"highlight_index": -1}]
        ),
        _colored(
            "b", ["blue", "green"], [{"highlight_index": 0}, {"highlight_index": 1}, {"highlight_index": 7}]
        ),
        _colored("c", True, [{"color": "green"}, {"color": "blue"}, {"highlight_index": -1}]),
    ]


def _leaf_indices(store: DiagramStore) -> list[list[int]]:
    return [[leaf.highlight_index for leaf in n.leaf_nodes()] for n in store.diagram.children]


def test_check_colors_remaps_file_palettes_to_the_merged_palette() -> None:
    """S7 (fix round WP6): a list palette is local to its file; ``colors: true`` gets real indices (not dummy 0)."""
    store = _store(_mixed_palette_files())
    assert store.highlight_colors == ["red", "blue", "green"]
    assert _leaf_indices(store) == [[1, 0, -1], [1, 2, 7], [2, 1, -1]]


def test_check_colors_is_idempotent_on_the_same_files() -> None:
    """S7: a list-palette file gets the merged palette, so a second ``set_networks`` on the same files is the identity."""
    files = _mixed_palette_files()
    store = _store(files)
    before = _leaf_indices(store)
    assert files[1].colors == ["red", "blue", "green"]
    store.set_networks(files)
    assert store.highlight_colors == ["red", "blue", "green"] and _leaf_indices(store) == before


def test_layout_does_not_mutate_list_palette_inputs() -> None:
    """S7: ``layout`` copies the files with input colours before ``check_colors`` remaps them."""
    from alluvial import layout

    files = _mixed_palette_files()
    layout(files)
    assert files[1].colors == ["blue", "green"]
    assert [n.highlight_index for n in files[1].nodes] == [0, 1, 7]


def test_color_module_ids_in_all_networks_clears_first() -> None:
    """S3 (fix round WP6): the registry restarts and hidden or uncoloured modules lose stale colours."""
    rows = [("1", "1:1", 0.4), ("2", "1:2", 0.4), ("3", "2:1", 0.2)]
    store = _store([net("a", rows), net("b", rows)])
    store.color_module(store.diagram.children[0].get_module("2"), "#123456")
    store.color_module_ids_in_all_networks()
    assert "#123456" not in store.highlight_colors
    assert store.highlight_colors == [C3_SINEBOW[0], C3_SINEBOW[1]]


def test_similar_modules_with_prototype_key_identifiers() -> None:
    """S5 (fix round WP6): identifiers like ``constructor`` and ``__proto__`` match like any other (TS ``Map``)."""
    rows = [("constructor", "1:1", 0.5, 1), ("__proto__", "1:2", 0.5, 2)]
    store = _store([net("a", rows), net("b", rows)])
    (match,) = store.diagram.children[0].get_module("1").get_similar_modules(RIGHT, 1)
    assert match.module.module_id == "1" and match.similarity == 1


def test_color_matching_is_idempotent() -> None:
    """E4: a second run gives the same colours (single-leaf modules are no longer re-created)."""
    rows = [("1", "1:1", 0.4), ("2", "1:2", 0.4), ("3", "2:1", 0.2)]
    store = _store([net("a", rows), net("b", rows)])
    store.color_matching_modules_in_all_networks()
    assert _module_indices(store) == [{"1": 0, "2": 1}] * 2
    store.color_matching_modules_in_all_networks()
    assert _module_indices(store) == [{"1": 0, "2": 1}] * 2


def test_recolour_single_leaf_module_keeps_name_order_and_flow() -> None:
    """E4/E5 (fix-plan finding 10): a recoloured single-leaf module keeps its object, name, position and flow."""
    rows = [("1", "1:1", 0.4), ("2", "1:2", 0.4), ("3", "2:1", 0.2)]
    store = _store([net("a", rows)])
    network = store.diagram.children[0]
    single = network.get_module("2")
    single.name = "solo"
    network.children.reverse()
    network.is_custom_sorted = True
    order = list(network.children)
    flow = single.flow
    store.color_module(single, "#ff0000")
    assert network.get_module("2") is single and single.name == "solo"
    assert network.children == order and single.flow == flow and single.highlight_index == 0
    leaf = single.get_leaf_nodes()[0]
    parents = (leaf.left_parent, leaf.right_parent)
    store.color_module(single, "#ff0000")  # E5: a no-op recolour does not touch the leaf
    assert (leaf.left_parent, leaf.right_parent) == parents


def test_store_highlight_index_registry() -> None:
    store = _store([net("a", [("1", "1:1", 1.0)])])
    assert store.get_highlight_index(store.default_highlight_color) == -1
    assert [store.get_highlight_index(c) for c in ("#f00", "#0f0", "#f00")] == [0, 1, 0]
    assert store.highlight_colors == ["#f00", "#0f0"]


def test_empty_store_does_not_lay_out() -> None:
    store = DiagramStore(LayoutOptions())
    store.set_networks([])
    assert store.diagram.children == [] and store.update_layout_calls == 0


def test_check_colors_keeps_a_huge_int_index() -> None:
    """S7 (WP6 review): an ``int`` index too large for a float is an integer outside the palette, kept as is
    (``Number.isInteger``), not an ``OverflowError``."""
    files = [_colored("a", ["red"], [{"highlight_index": 10**400}, {"highlight_index": 0}])]
    store = _store(files)
    assert _leaf_indices(store) == [[10**400, 0]]
