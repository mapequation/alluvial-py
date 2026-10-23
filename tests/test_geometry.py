"""``build_geometry`` and ``layout()`` against the TS fixtures (via ``helpers_geometry.geometry_from_fixture``)."""

from __future__ import annotations

import math

import pytest
from conftest import TESTS_DIR, V2_SCENARIOS, assert_matches, fixture_data_paths, load_fixture
from helpers_geometry import geometry_from_fixture
from test_engine_fixtures import replay_fixture

from alluvial.geometry import AlluvialGeometry, HighlightLabel, build_geometry
from alluvial.layout import LayoutOptions, layout

pytestmark = pytest.mark.filterwarnings("ignore:.*identifier.*shared:UserWarning")


def _assert_geometry_equal(actual: AlluvialGeometry, expected: AlluvialGeometry) -> None:
    # name_candidates is renderer-only (not in the TS fixtures); test_name_candidates_* cover it. The per-name
    # highlight fields are aligned with it; test_name_highlight_matches_fixture covers them.
    res = assert_matches(
        actual.to_dict(),
        expected.to_dict(),
        ignore={"name_candidates", "name_highlight_indices", "name_insignificant"},
    )
    assert res.non_bitwise == 0
    for a, e in zip(actual.streamlines, expected.streamlines):
        assert a.svg_path() == e.svg_path()


def test_build_geometry_matches_fixture(scenario: str) -> None:
    fx = load_fixture(scenario)
    store, _, _ = replay_fixture(fx)
    geom = build_geometry(store.diagram, store.options, palette=tuple(store.highlight_colors))
    _assert_geometry_equal(geom, geometry_from_fixture(fx))


def test_build_geometry_svg_paths_match_fixture_strings() -> None:
    fx = load_fixture("science-stree__nameColored")
    store, _, _ = replay_fixture(fx)
    geom = build_geometry(store.diagram, store.options)
    expected = [link["path"] for n in fx["networks"] for link in n["links"]]
    assert [s.svg_path() for s in geom.streamlines] == expected


# layout() with only public arguments reproduces the store-driven fixtures.
@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("planted-ftree__default", {"colors": None}),
        ("planted-ftree__colored", {"colors": "similarity"}),
        ("planted-ftree__colorModuleIds", {"colors": "module_id"}),
        ("planted-ftree__colorNodes", {"colors": "nodes"}),
        ("states-tree__colored", {"colors": "similarity"}),
        ("debug5-stree__nameColored", {"identifier": "name", "colors": "similarity"}),
        ("science-stree__nameColored", {"identifier": "name", "colors": "similarity"}),
    ],
)
def test_layout_matches_fixture(name: str, kwargs: dict) -> None:
    fx = load_fixture(name)
    options = LayoutOptions.from_ts(fx["inputs"]["options"])
    geom = layout([str(p) for p in fixture_data_paths(fx)], **kwargs, **vars(options))
    _assert_geometry_equal(geom, geometry_from_fixture(fx))


def test_layout_accepts_network_files_and_names() -> None:
    from alluvial.io import read

    files = [read(TESTS_DIR / "data" / f"planted_t{i}.ftree") for i in range(3)]
    geom = layout(files, names=["a", "b", "c"])
    assert [n.name for n in geom.networks] == ["a", "b", "c"]
    assert [f.name for f in files] == [f"planted_t{i}.ftree" for i in range(3)]
    reference = layout([TESTS_DIR / "data" / f"planted_t{i}.ftree" for i in range(3)])
    assert geom.streamlines == reference.streamlines


def test_layout_rejects_bad_inputs() -> None:
    path = TESTS_DIR / "data" / "planted_t0.ftree"
    with pytest.raises(ValueError, match="duplicate network id"):
        layout([path, path], ids=["a", "a"])
    with pytest.raises(ValueError, match="colors"):
        layout([path], colors="rainbow")
    with pytest.raises(ValueError, match="names"):
        layout([path], names=["a", "b"])


def test_to_dict_round_trip() -> None:
    fx = load_fixture("planted-ftree__colorNodes")
    store, _, _ = replay_fixture(fx)
    geom = build_geometry(store.diagram, store.options, palette=tuple(store.highlight_colors))
    assert AlluvialGeometry.from_dict(geom.to_dict()) == geom


def test_js_ceil_matches_math_ceil_semantics_of_js() -> None:
    from alluvial.geometry import js_ceil

    assert js_ceil(2.1) == 3 and isinstance(js_ceil(2.1), int)
    assert math.isnan(js_ceil(math.nan))
    assert js_ceil(math.inf) == math.inf
    assert js_ceil(6.944444437133705e20) == 6.944444437133705e20
    assert isinstance(js_ceil(6.944444437133705e20), float)


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_layout_rejects_a_nan_flow() -> None:
    """A NaN flow used to make every module height NaN (and the sort order V8-specific); both engines now reject it
    at load (fix round E9)."""
    with pytest.raises(ValueError, match="node 1 has no finite flow"):
        layout([TESTS_DIR / "data" / "nan_t0.tree", TESTS_DIR / "data" / "zeroflow_t0.tree"])


def test_layout_with_huge_height_labels_all_leaves() -> None:
    geom = layout([TESTS_DIR / "data" / f"planted_t{i}.ftree" for i in range(2)], height=1e22)
    module = geom.networks[0].modules[0]
    assert module.label is not None
    assert len(module.largest_leaf_names) == module.label.text.count("\n") + 1 > 5


def test_name_candidates_extend_the_parity_names() -> None:
    from alluvial.geometry import NAME_CANDIDATES

    fx = load_fixture("science-stree__nameColored")
    store, _, _ = replay_fixture(fx)
    geom = build_geometry(store.diagram, store.options)
    labelled = [m for n in geom.networks for m in n.modules if m.label is not None]
    assert labelled
    for m in labelled:
        assert m.name_candidates[: len(m.largest_leaf_names)] == m.largest_leaf_names
        assert len(m.largest_leaf_names) <= len(m.name_candidates) <= NAME_CANDIDATES
    assert any(len(m.name_candidates) > len(m.largest_leaf_names) for m in labelled)
    unlabelled = [m for n in geom.networks for m in n.modules if m.label is None]
    assert all(m.name_candidates == () for m in unlabelled)
    # Round trip, and from_dict of an older dict without the key.
    assert AlluvialGeometry.from_dict(geom.to_dict()) == geom
    d = geom.to_dict()
    for n in d["networks"]:
        for m in n["modules"]:
            del m["name_candidates"]
    assert all(m.name_candidates == () for n in AlluvialGeometry.from_dict(d).networks for m in n.modules)


# --- v2: hierarchy and highlight fields ------------------------------------------------------------------------

NAME_HIGHLIGHT_SCENARIOS = [s for s in V2_SCENARIOS if load_fixture(s)["inputs"].get("labelNameHighlight")]


@pytest.mark.parametrize("name", NAME_HIGHLIGHT_SCENARIOS)
def test_name_highlight_matches_fixture(name: str) -> None:
    """``name_highlight_indices``/``name_insignificant`` start with the fixture's per-name values (TS
    ``labelNameHighlight``; aggregated names have no ``insignificant``, i.e. False)."""
    fx = load_fixture(name)
    store, _, _ = replay_fixture(fx)
    geom = build_geometry(store.diagram, store.options, palette=tuple(store.highlight_colors))
    checked = 0
    for n, gn in zip(fx["networks"], geom.networks, strict=True):
        visible = [m for m in n["modules"] if m["visible"]]
        for m, gm in zip(visible, gn.modules, strict=True):
            names = m["label"]["names"]
            assert len(gm.name_highlight_indices) == len(gm.name_insignificant)
            assert len(gm.name_highlight_indices) == len(gm.name_candidates or gm.largest_leaf_names)
            k = len(names)
            assert list(gm.name_highlight_indices[:k]) == [e["highlightIndex"] for e in names]
            assert list(gm.name_insignificant[:k]) == [bool(e["insignificant"]) for e in names]
            checked += k
    assert checked > 0
    assert any(i >= 0 for n in geom.networks for m in n.modules for i in m.name_highlight_indices)


def test_v2_geometry_round_trip_and_v1_defaults() -> None:
    fx = load_fixture("multilevel-tree__level3")
    store, _, _ = replay_fixture(fx)
    labels = (HighlightLabel("a", 0, "#ff0000"), HighlightLabel("b", -1, "#b6b69f"))
    geom = build_geometry(store.diagram, store.options, highlight_labels=labels)
    assert geom.highlight_labels == labels
    assert any(n.outlines for n in geom.networks)
    assert {m.level for n in geom.networks for m in n.modules} == {1, 2, 3}
    assert AlluvialGeometry.from_dict(geom.to_dict()) == geom
    # A v1 dict (no v2 keys) still loads, with the v1 defaults.
    d = geom.to_dict()
    del d["highlight_labels"]
    for n in d["networks"]:
        del n["outlines"]
        for m in n["modules"]:
            for key in ("level", "max_level", "order", "name_highlight_indices", "name_insignificant"):
                del m[key]
    old = AlluvialGeometry.from_dict(d)
    assert old.highlight_labels == () and all(n.outlines == () for n in old.networks)
    assert all(m.level == 1 and m.order is None for n in old.networks for m in n.modules)


def test_flat_geometry_has_no_outlines_and_visible_order() -> None:
    geom = layout([TESTS_DIR / "data" / f"planted_t{i}.ftree" for i in range(3)])
    for n in geom.networks:
        assert n.outlines == ()
        assert [m.order for m in n.modules] == list(range(len(n.modules)))
        assert all(m.level == 1 for m in n.modules)


def test_mixed_parent_and_submodule_has_an_enclosing_outline() -> None:
    """Fix round E15a (v2-hierarchy.md §8.4): a module shown together with one of its sub-modules (state reachable
    only through input module levels) no longer makes the tree throw. The parent's tree node is a non-leaf node whose
    outline encloses the parent module and its sub-module, whatever the module order."""
    from alluvial.io import read

    nf = read(TESTS_DIR / "data" / "multilevel_t0.tree")
    first_top = nf.nodes[0].path.split(":")[0] if isinstance(nf.nodes[0].path, str) else None
    assert first_top is not None
    deep = [n for n in nf.nodes if n.path.split(":")[0] == first_top]
    deep[0].module_level = 2  # one leaf of the first top module at level 2, the rest at level 1
    from alluvial.engine import DiagramStore

    store = DiagramStore(LayoutOptions(flow_threshold=0))
    store.set_networks([nf])
    network = store.diagram.children[0]
    parent = network.get_module(first_top)
    sub = next(m for m in network.children if m.module_level == 2)
    assert parent is not None and parent.is_visible and sub.is_visible
    for order in ([sub, parent], [parent, sub]):  # both creation orders give the same outline
        network.set_module_order(order)
        store.diagram.update_layout(store.options)
        geom = build_geometry(store.diagram, store.options)
        outlines = geom.networks[0].outlines
        assert len(outlines) == 1
        (outline,) = outlines
        for module in (parent, sub):
            assert outline.y <= module.y and module.y + module.height <= outline.y + outline.height
