"""Unit tests of the v2 engine pieces that the fixtures do not pin directly (v2-hierarchy.md §12.3 "unit tests",
v2-highlight.md §9.6): refusals, ``move_item``, the module-level helper's edge cases, ``apply_expand_list``,
``apply_highlight`` and the registry helpers."""

from __future__ import annotations

import math
import warnings

import pytest
from conftest import TESTS_DIR, assert_matches

from alluvial.engine import DiagramStore
from alluvial.engine._utils import move_item
from alluvial.engine.store import HIGHLIGHT_KEY
from alluvial.io import read
from alluvial.layout import LayoutOptions
from alluvial.palette import C3_SINEBOW

DATA = TESTS_DIR / "data"


def _store(*names: str, **options) -> DiagramStore:
    files = []
    for name in names:
        nf = read(DATA / name)
        nf.id = name.rsplit(".", 1)[0]
        files.append(nf)
    store = DiagramStore(LayoutOptions(**options))
    store.set_networks(files)
    return store


def _state(store: DiagramStore) -> list:
    return [
        (n.is_custom_sorted, [(m.module_id, m.module_level, m.y, m.height) for m in n.children])
        for n in store.diagram.children
    ]


@pytest.mark.parametrize(
    ("from_index", "to_index", "expected"),
    [
        (0, 1, [1, 0, 2, 3]),
        (1, 0, [1, 0, 2, 3]),
        (3, 2, [0, 1, 3, 2]),
        (-1, 0, [3, 0, 1, 2]),  # negative from: counts from the end
        (0, -1, [1, 2, 3, 0]),  # negative to: len + to with the length before the removal
        (0, 10, [1, 2, 3, 0]),  # past the end appends
        (4, 0, [0, 1, 2, 3]),  # out of range: no-op
        (-5, 0, [0, 1, 2, 3]),
    ],
)
def test_move_item(from_index: int, to_index: int, expected: list[int]) -> None:
    arr = [0, 1, 2, 3]
    move_item(arr, from_index, to_index)
    assert arr == expected


@pytest.mark.filterwarnings("ignore:.*(expanded|module level):UserWarning")
def test_refused_ops_return_false_and_change_nothing() -> None:
    store = _store("planted_t0.ftree", "planted_t1.ftree")
    network = store.diagram.children[0]
    before = _state(store)
    calls = store.update_layout_calls
    module = network.children[0]
    with pytest.warns(UserWarning, match="can't be expanded to level 2"):
        assert store.expand(module) is False  # 2-level tree: every leaf is at level 2
    with pytest.warns(UserWarning, match="already at module level 1"):
        assert store.regroup(module) is False
    with pytest.warns(UserWarning, match="already at the bottom"):
        assert store.move_module(network.children[0], "down") is False
    with pytest.warns(UserWarning, match="already at the top"):
        assert store.move_module(network.children[-1], "up") is False
    assert _state(store) == before
    assert store.update_layout_calls == calls
    with pytest.raises(RuntimeError, match="expand refused"):
        store.apply({"op": "expand", "networkIndex": 0, "moduleIndex": 0})
    with pytest.raises(RuntimeError, match="expected True"):
        store.apply({"op": "regroup", "networkIndex": 0, "moduleIndex": 0, "result": True})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert (
            store.apply(
                {
                    "op": "moveModule",
                    "networkIndex": 0,
                    "moduleIndex": 0,
                    "direction": "down",
                    "result": False,
                }
            )
            is False
        )


def test_move_lays_out_without_calc_flow() -> None:
    store = _store("multilevel_t0.tree", "multilevel_t1.tree")
    network = store.diagram.children[0]
    first, second = network.children[0], network.children[1]
    calls = store.update_layout_calls
    assert store.move_module(first, "up") is True
    assert network.is_custom_sorted
    assert network.children[0] is second and network.children[1] is first
    assert store.update_layout_calls == calls + 1
    assert first.y < second.y  # stacked from the bottom: index 1 sits above index 0
    store.reset_layout()
    assert not network.is_custom_sorted
    assert network.children[0] is first


def test_module_level_on_two_level_trees_issues_no_ops() -> None:
    store = _store("planted_t0.ftree", "planted_t1.ftree", "planted_t2.ftree")
    assert store.apply_module_level(3) == []
    store = _store("states_t0.tree", "states_t1.tree")
    assert store.apply_module_level([4, 2]) == []


def test_module_level_validation() -> None:
    store = _store("multilevel_t0.tree", "multilevel_t1.tree")
    for bad in (0, True, 2.0, [2], [2, 2, 2], "2", [2, 0], [2, None]):
        with pytest.raises(ValueError, match="module_level"):
            store.apply_module_level(bad)
    assert store.apply_module_level(1) == []


def test_module_level_is_idempotent_and_only_expands() -> None:
    store = _store("multilevel_t0.tree", "multilevel_t1.tree", "multilevel_t2.tree")
    calls = store.update_layout_calls
    ops = store.apply_module_level(3)
    assert ops == [{"op": "setModuleLevel", "levels": [3, 3, 3]}]
    assert store.update_layout_calls == calls + 1  # fix round B2: one layout for the whole batch
    assert store.apply_module_level(3) == []
    assert store.apply_module_level(2) == []  # never regroups
    assert max(m.module_level for n in store.diagram.children for m in n.children) == 3


_MIXED_TREE = """# path flow name node_id
1:1:1:1 0.2 "a" 1
1:1:2:1 0.15 "b" 2
1:2:1 0.25 "c" 3
2:1 0.2 "d" 4
2:2:1 0.2 "e" 5
"""


def _mixed_store(tmp_path, n: int = 2) -> DiagramStore:
    files = []
    for i in range(n):
        path = tmp_path / f"mixed{i}.tree"
        path.write_text(_MIXED_TREE)
        nf = read(path)
        nf.id = f"mixed{i}"
        files.append(nf)
    store = DiagramStore(LayoutOptions(flow_threshold=0))
    store.set_networks(files)
    return store


def test_can_expand_carries_the_expand_refusal_rule(tmp_path) -> None:
    """Fix round H4: module 2 mixes a leaf at level 2 with one at level 3, so it is not a leaf module, but
    ``expand`` refuses it; ``can_expand`` says so."""
    store = _mixed_store(tmp_path)
    network = store.diagram.children[0]
    one, two = network.get_module("1"), network.get_module("2")
    assert one.can_expand
    assert not two.is_leaf_module and not two.can_expand
    with pytest.warns(UserWarning, match="can't be expanded"):
        assert not store.expand(two)


def test_set_module_level_expands_in_rounds_with_one_layout(tmp_path) -> None:
    """Fix round B2: rounds without intermediate layouts, one ``update_layout`` at the end, idempotent."""
    store = _mixed_store(tmp_path)
    calls = store.update_layout_calls
    assert store.set_module_level([3, 2])
    assert store.update_layout_calls == calls + 1
    a, b = store.diagram.children
    assert sorted(m.module_id for m in a.children) == ["1:1:1", "1:1:2", "1:2", "2"]
    assert sorted(m.module_id for m in b.children) == ["1:1", "1:2", "2"]
    assert not store.set_module_level([3, 2])
    assert not store.set_module_level(1)  # never regroups
    assert store.update_layout_calls == calls + 1
    assert store.apply_module_level(4) == [{"op": "setModuleLevel", "levels": [4, 4]}]


def test_apply_expand_list() -> None:
    store = _store("multilevel_t0.tree", "multilevel_t1.tree")
    store.apply_expand_list([(0, "1"), ("multilevel_t1", "1"), ("multilevel_t1", "1:1")])
    n0, n1 = store.diagram.children
    assert n0.get_module("1") is None and n0.get_module("1:1") is not None
    assert n1.get_module("1") is None and n1.get_module("1:1") is None
    assert n1.get_module("1:1:1") is not None
    with pytest.raises(ValueError, match="no module"):
        store.apply_expand_list([(0, "99")])
    with pytest.raises(ValueError, match="no network"):
        store.apply_expand_list([(5, "1")])
    with pytest.raises(ValueError, match="no network"):
        store.apply_expand_list([("nope", "1")])
    flat = _store("planted_t0.ftree")
    with pytest.raises(ValueError, match=r"cannot expand module '1'.*can't be expanded to level 2"):
        flat.apply_expand_list([(0, "1")])


def test_apply_highlight_hlskip_colours_every_labelled_node() -> None:
    """E4: the walk no longer skips a module after recolouring a single-leaf one, so no node stays gray."""
    store = _store("hlskip_t0.tree", "hlskip_t1.tree", "hlskip_t2.tree")
    label_of = {"3": 0, "4": 0, "1": 1}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        indices = store.apply_highlight(lambda leaf: label_of.get(leaf.identifier), ["#ff0000", "#0000ff"])
    assert indices == [0, 1]
    assert store.highlight_colors == ["#ff0000", "#0000ff"]
    got = [{leaf.identifier: leaf.highlight_index for leaf in n.leaf_nodes()} for n in store.diagram.children]
    assert got == [{"1": 1, "2": -1, "3": 0, "4": 0}] * 3
    leaves = [leaf for n in store.diagram.children for leaf in n.leaf_nodes()]
    assert all(isinstance(leaf.metadata, dict) for leaf in leaves)
    assert [leaf.metadata.get(HIGHLIGHT_KEY) for leaf in leaves if leaf.identifier in label_of] == [
        str(label_of[leaf.identifier]) for leaf in leaves if leaf.identifier in label_of
    ]


def test_apply_highlight_shared_and_default_colors() -> None:
    store = _store("planted_t0.ftree", "planted_t1.ftree")
    identifiers = [leaf.identifier for leaf in store.diagram.children[0].leaf_nodes()]
    label_of = {identifiers[0]: 0, identifiers[1]: 1, identifiers[2]: 2}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        indices = store.apply_highlight(
            lambda leaf: label_of.get(leaf.identifier), ["#ff0000", "#ff0000", store.default_highlight_color]
        )
    assert indices == [0, 0, -1]


def test_registry_helpers() -> None:
    store = _store("planted_t0.ftree")
    assert store.get_highlight_color(None) is None
    assert store.get_highlight_color(0) is None
    assert store.get_highlight_color(-1) == store.default_highlight_color
    assert store.get_highlight_color(-1, "#000") == "#000"
    store.set_highlight_colors(["a", "b"])
    assert store.get_highlight_color(1) == "b" and store.get_highlight_color(-2) is None
    store.set_default_highlight_color("a")
    assert store.get_highlight_index("a") == -1 and store.get_highlight_index("b") == 1
    store.set_selected_scheme(["x", "y"])
    assert store.selected_scheme == ["x", "y"]
    store.set_selected_scheme("C3 Sinebow")
    assert store.selected_scheme == list(C3_SINEBOW)
    with pytest.raises(ValueError, match="scheme"):
        store.set_selected_scheme("No such scheme")


def test_metadata_ops_skip_a_network_without_leaves() -> None:
    """E12 (fix round WP6): ``haveMetadata`` is False for a network without leaves (TS threw a TypeError)."""
    store = _store("planted_t0.ftree")
    network = store.diagram.children[0]
    for module in list(network.children):
        network.remove_child(module)
    assert not network.have_metadata and not network.is_multilayer and not network.is_higher_order
    store.color_categorical_metadata("c", {"a": "#ff0000"})
    assert store.highlight_colors == ["#ff0000"]


def test_color_real_metadata_last_bin_includes_its_upper_edge() -> None:
    """S6 (fix round WP6): a value equal to the last bin's ``x1`` (the data maximum) gets the last colour."""
    nf = read(DATA / "planted_t0.ftree")
    for i, node in enumerate(nf.nodes):
        node.metadata = {"x": float(i % 3)}  # 0, 1, 2
    store = DiagramStore(LayoutOptions())
    store.set_networks([nf])
    bins = [{"x0": 0, "x1": 1, "color": "#aa0000"}, {"x0": 1, "x1": 2, "color": "#00aa00"}]
    store.color_real_metadata("x", bins)
    network = store.diagram.children[0]
    by_value = {
        leaf.metadata["x"]: leaf.highlight_index
        for m in network.children
        if m.is_visible
        for leaf in m.get_leaf_nodes()
    }
    assert by_value == {0.0: 0, 1.0: 1, 2.0: 1}


def test_have_metadata_when_the_first_leaf_has_none() -> None:
    """E12 (fix round WP6): ``haveMetadata`` is True when some leaf has metadata, not only the first one."""
    nf = read(DATA / "planted_t0.ftree")
    for node in nf.nodes:
        node.metadata = {"c": "a"}
    store = DiagramStore(LayoutOptions())
    store.set_networks([nf])
    network = store.diagram.children[0]
    first = next(network.leaf_nodes())
    first.metadata = None
    assert network.have_metadata
    store.color_categorical_metadata("c", {"a": "#ff0000"})
    visible = [leaf for m in network.children if m.is_visible for leaf in m.get_leaf_nodes()]
    assert first.highlight_index == -1
    assert all(leaf.highlight_index == 0 for leaf in visible if leaf is not first)


@pytest.mark.parametrize(
    ("metadata", "shown"),
    [("abc", "abc"), (5, "5"), (1.5, "1.5"), (True, "true")],
    ids=["str", "int", "float", "true"],
)
def test_metadata_ops_throw_on_truthy_non_object_metadata(metadata, shown) -> None:
    """TS ``name in node.metadata`` throws for a truthy primitive (a JSON node ``metadata`` that is not an object);
    falsy values are skipped and arrays are read by index (fixtures ``planted-ftree__array*``)."""
    nf = read(DATA / "planted_t0.ftree")
    for node in nf.nodes:
        node.metadata = metadata
    store = DiagramStore(LayoutOptions())
    store.set_networks([nf])
    with pytest.raises(TypeError, match=f"Cannot use 'in' operator to search for 'c' in {shown}$"):
        store.color_categorical_metadata("c", {"a": "#ff0000"})
    for falsy in (0, "", False, math.nan):
        for leaf in store.diagram.children[0].leaf_nodes():
            leaf.metadata = falsy
        store.color_real_metadata("c", [{"x0": 0, "x1": 1, "color": "#ff0000"}])


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize("seed", range(40))
def test_apply_highlight_equals_categorical_metadata_on_input_nodes(seed: int, tmp_path) -> None:
    """Property (v2-highlight.md §9.6): ``apply_highlight`` (labels written onto the leaves after the build and the
    v2 ops) gives the same state as the harness ``highlight`` macro (labels as input-node metadata, then
    ``colorCategoricalMetadata``), which the TS fixtures pin. Random fuzz cases (gen.py --v2) and random labels."""
    import random

    from test_engine_fixtures import Trace, dump_store
    from test_fuzz_parity import _apply_raw, _load_gen, _resolve

    case = _load_gen().make_case(seed, tmp_path, v2=True)
    rng = random.Random(f"highlight-{seed}")

    def run(with_input_metadata: bool):
        files = []
        for path in case["files"]:
            nf = read(path, identifier=case.get("identifier", "id"))
            nf.id = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            for node in nf.nodes:  # JSON inputs can carry metadata; the property is about the labels alone
                node.metadata = None
            files.append(nf)
        identifiers = sorted(
            {node.identifier for nf in files for node in nf.nodes if node.identifier is not None}
        )
        rng.seed(f"labels-{seed}")
        labels = {i: rng.randrange(3) for i in identifiers if rng.random() < 0.4}
        colors = [rng.choice(["#ff0000", "#00ff00", "#0000ff", "#b6b69f"]) for _ in range(3)]
        if with_input_metadata:
            for nf in files:
                for node in nf.nodes:
                    k = labels.get(node.identifier)
                    node.metadata = {} if k is None else {HIGHLIGHT_KEY: str(k)}
        trace = Trace()
        store = DiagramStore(LayoutOptions.from_ts(case["options"]), trace=trace)
        store.set_networks(files)
        for op in case["ops"]:
            if op["op"] != "highlight":  # the fuzz macro would relabel the leaves under test
                _apply_raw(store, _resolve(store, op))
        if with_input_metadata:
            store.color_categorical_metadata(HIGHLIGHT_KEY, {str(k): c for k, c in enumerate(colors)})
        else:
            store.apply_highlight(lambda leaf: labels.get(leaf.identifier), colors)
        inputs = {
            "files": case["files"],
            "labelOptions": {"fontSize": 8, "aggregateStateNames": True, "showModuleNames": True},
        }
        return dump_store(store, trace, inputs, files)

    try:
        expected = run(True)
    except Exception:  # the case itself fails (TS throws too); nothing to compare
        pytest.skip("case raises")
    res = assert_matches(run(False), expected)
    assert res.non_bitwise == 0
