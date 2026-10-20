"""Public API of v4: ``layout(module_order=..., module_names=...)`` arguments, their errors, and ``draw`` with names.
Bit parity with TS is in ``test_v4_fixtures``."""

from __future__ import annotations

import warnings
from typing import Any

import pytest
from conftest import DATA_DIR
from test_api_v3 import assert_same_diagram

import alluvial
from alluvial import ModuleInfo, layout

MULTILEVEL = [str(DATA_DIR / f"multilevel_t{t}.tree") for t in range(3)]
PLANTED = [str(DATA_DIR / f"planted_t{t}.ftree") for t in range(3)]


def _order(geom: Any, i: int) -> list[str]:
    """Visible module ids of network ``i`` bottom to top (descending y in SVG coordinates)."""
    return [m.id for m in sorted(geom.networks[i].modules, key=lambda m: -m.y)]


def test_module_order_positions_and_ellipsis() -> None:
    base = layout(MULTILEVEL)
    assert _order(base, 0) == ["1", "2", "3", "4"]
    geom = layout(MULTILEVEL, module_order={0: ["3", "1"], "multilevel_t2": [..., "1"], 1: ["2", ..., "1"]})
    assert _order(geom, 0) == ["3", "1", "2", "4"]
    assert _order(geom, 1) == ["2", "3", "1"]
    assert _order(geom, 2) == ["2", "3", "4", "1"]
    # the literal string "..." works as the placeholder too; an already sorted order changes nothing
    assert layout(MULTILEVEL, module_order={2: ["...", "1"]}) == layout(
        MULTILEVEL, module_order={2: [..., "1"]}
    )
    assert layout(MULTILEVEL, module_order={0: ["1", "2"], 1: [...]}) == base


def test_module_order_with_module_level_uses_sub_module_ids() -> None:
    geom = layout(MULTILEVEL, module_level=2, module_order={0: ["2:1", "1:3", ...]})
    assert _order(geom, 0)[:3] == ["2:1", "1:3", "1:1"]


@pytest.mark.parametrize(
    ("order", "error", "match"),
    [
        ({5: ["1"]}, ValueError, r"module_order: no network 5 \(the diagram has 3 networks\)"),
        ({"nope": ["1"]}, ValueError, r"module_order: no network 'nope' \(network ids: 'multilevel_t0'"),
        ({0: ["9"]}, ValueError, r"module_order: no module '9' in network 'multilevel_t0'"),
        ({0: ["1:1"]}, ValueError, r"no module '1:1' .*expand its parent module '1' first"),
        ({0: ["1", "1"]}, ValueError, r"module '1' is listed twice for network 'multilevel_t0'"),
        ({0: ["1", ..., ...]}, ValueError, r"more than one '...'"),
        ({0: ["1"], "multilevel_t0": ["2"]}, ValueError, r"network 'multilevel_t0' is given twice"),
        ({0: "12"}, TypeError, r"must be a list of module ids"),
        ({0: [1]}, TypeError, r"module ids are strings"),
        ({1.5: ["1"]}, TypeError, r"keys must be network indices or ids"),
        ([("0", ["1"])], TypeError, r"module_order must be a mapping"),
    ],
)
def test_module_order_errors(order: Any, error: type, match: str) -> None:
    with pytest.raises(error, match=match):
        layout(MULTILEVEL, module_order=order)


def test_module_order_rejects_hidden_modules() -> None:
    with pytest.raises(ValueError, match=r"module '1' in network 'planted_t1' is not shown .*flow threshold"):
        layout(PLANTED, flow_threshold=0.4, module_order={1: ["1", "2"]})


def test_module_names_mapping_and_callable() -> None:
    geom = layout(MULTILEVEL, module_names={(0, "1"): "Alpha", ("multilevel_t2", "4"): "Four"})
    names = {(m.network_index, m.id): m.name for n in geom.networks for m in n.modules if m.name}
    assert names == {(0, "1"): "Alpha", (2, "4"): "Four"}

    seen: list[ModuleInfo] = []

    def name_of(info: ModuleInfo) -> str | None:
        seen.append(info)
        return f"top {info.node_names[0]}" if info.network_index == 0 and info.id == "2" else None

    geom = layout(MULTILEVEL, module_names=name_of)
    assert len(seen) == 4 + 3 + 4
    info = seen[1]
    assert (info.network_index, info.network_id, info.id, info.path, info.level, info.visible) == (
        0,
        "multilevel_t0",
        "2",
        (2,),
        1,
        True,
    )
    assert info.flow > 0 and info.node_names
    (named,) = [m for n in geom.networks for m in n.modules if m.name]
    assert named.name == f"top {info.node_names[0]}"
    # ``label`` keeps the leaf names (TS parity); the name is what draw shows
    assert named.label is not None and named.name not in named.label.text


@pytest.mark.parametrize(
    ("names", "error", "match"),
    [
        ({(3, "1"): "x"}, ValueError, r"module_names: no network 3"),
        ({("x", "1"): "x"}, ValueError, r"module_names: no network 'x'"),
        ({(0, "7"): "x"}, ValueError, r"module_names: no module '7' in network 'multilevel_t0'"),
        (
            {(0, "1"): "a", ("multilevel_t0", "1"): "b"},
            ValueError,
            r"module '1' of network 'multilevel_t0' is named twice",
        ),
        ({(0, 1): "x"}, TypeError, r"keys must be \(network index or id, module id string\) pairs"),
        ({0: "x"}, TypeError, r"keys must be"),
        ({(0, "1"): 3}, TypeError, r"must be a string"),
        (["x"], TypeError, r"module_names must be a mapping"),
        (lambda info: 3, TypeError, r"callable must return a string or None"),
    ],
)
def test_module_names_errors(names: Any, error: type, match: str) -> None:
    with pytest.raises(error, match=match):
        layout(MULTILEVEL, module_names=names)


def test_saved_names_and_order_are_restored(tmp_path: Any) -> None:
    kwargs = {"module_order": {0: ["2", ...]}, "module_names": {(0, "1"): "A"}}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = alluvial.save_diagram(MULTILEVEL, tmp_path / "w.zip", **kwargs)
    original = layout(MULTILEVEL, **kwargs)
    assert_same_diagram(layout(alluvial.read(out)), original)
    assert _order(original, 0)[0] == "2"
    # explicit module_order / module_names replace the stored ones
    assert _order(layout([out], module_order={0: ["3", ...]}), 0)[0] == "3"
    renamed = layout([out], module_names={(0, "1"): "B"})
    assert {m.name for m in renamed.networks[0].modules if m.name} == {"B"}
    # restore_state=False loads the files as plain Infomap JSON (colours and levels kept)
    plain = layout([out], restore_state=False)
    assert not any(m.name for n in plain.networks for m in n.modules)


def test_plot_routes_module_order_and_names() -> None:
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ax = alluvial.plot(MULTILEVEL, module_order={0: ["4"]}, module_names={(0, "4"): "Named four"})
    texts = [t.get_text() for t in ax.texts]
    assert "Named four" in texts
    plt.close(ax.figure)


def test_network_names_given_with_names_are_keys() -> None:
    names = ["2021", "2022", "2023"]
    by_name = layout(
        MULTILEVEL, names=names, module_order={"2021": ["3", ...]}, module_names={("2023", "1"): "A"}
    )
    by_index = layout(MULTILEVEL, names=names, module_order={0: ["3", ...]}, module_names={(2, "1"): "A"})
    assert by_name == by_index
    assert _order(by_name, 0)[0] == "3"
    # an int is always an index; the error points to the string form of a matching name
    with pytest.raises(
        ValueError, match=r"no network 2021 \(the diagram has 3 networks; .*pass the string '2021'"
    ):
        layout(MULTILEVEL, names=names, module_order={2021: ["1"]})
    # the error lists the names too; a name shared by several networks is not a key
    with pytest.raises(
        ValueError, match=r"no network 'x' \(network ids: .*; names: '2021', '2022', '2023'\)"
    ):
        layout(MULTILEVEL, names=names, module_order={"x": ["1"]})
    with pytest.raises(ValueError, match=r"3 networks are named 'y', use an index or a network id"):
        layout(MULTILEVEL, names=["y", "y", "y"], module_order={"y": ["1"]})


# --- fix round B1: module_order is one setModuleOrder (one layout) ------------------------------------------------


def _store(paths: list[str], **kwargs: Any) -> Any:
    from alluvial.layout import _build_store, _layout_arguments

    return _build_store(paths, **_layout_arguments(dict(kwargs)))[0]


def test_module_order_issues_one_set_module_order_op() -> None:
    store = _store(MULTILEVEL)
    calls = store.update_layout_calls
    ops = store.apply_module_order([(1, ["3", "1"]), (0, ["2", "..."])])
    # networks ascending, each with its full visible target bottom to top; one layout for all of them
    assert ops == [{"op": "setModuleOrder", "order": [[0, ["2", "1", "3", "4"]], [1, ["3", "1", "2"]]]}]
    assert store.update_layout_calls == calls + 1
    for network_index, ids in ops[0]["order"]:
        network = store.diagram.children[network_index]
        assert network.is_custom_sorted
        assert [m.module_id for m in network.visible_children] == ids
        assert [m.index for m in network.visible_children] == list(range(len(ids)))  # E7a: fresh index
    # a target equal to the current order issues no op, lays out nothing and does not freeze
    assert store.apply_module_order([(2, ["..."])]) == []
    assert store.update_layout_calls == calls + 1
    assert not store.diagram.children[2].is_custom_sorted


def test_set_module_order_lists_hidden_modules_and_skips_foreign_ones() -> None:
    store = _store(PLANTED, flow_threshold=0.4)
    network, other = store.diagram.children[0], store.diagram.children[1]
    hidden = [m for m in network.children if not m.is_visible]
    visible = [m for m in network.children if m.is_visible]
    assert hidden and len(visible) > 1
    target = [*hidden[::-1], *visible[::-1], other.children[0], visible[0]]  # foreign module and a repeat
    assert store.set_module_order([(network, target)])
    # the layout re-partitions children into visible + hidden, keeping each part's listed order
    assert network.children == [*visible[::-1], *hidden[::-1]]
    assert all(m.margin == 0 for m in hidden)  # E7b
    # unchanged order: frozen anyway, but no layout
    calls = store.update_layout_calls
    network.is_custom_sorted = False
    assert not store.set_module_order([(network, list(network.children))])
    assert network.is_custom_sorted and store.update_layout_calls == calls


def test_module_order_on_science_level2_is_fast() -> None:
    """Reversing 40 of the 429 visible modules at ``module_level=2`` took 780 moves (one layout each, 85 s in WP7); it is
    one layout now."""
    import time

    science = [str(DATA_DIR / f"science{y}_2y.stree") for y in (2001, 2003, 2005, 2007)]
    store = _store(science, colors=None, module_level=2)
    ids = [m.module_id for m in store.diagram.children[0].visible_children]
    assert len(ids) == 429
    start = time.perf_counter()
    ops = store.apply_module_order([(0, ids[:40][::-1])])
    elapsed = time.perf_counter() - start
    assert [op["op"] for op in ops] == ["setModuleOrder"]
    assert [m.module_id for m in store.diagram.children[0].visible_children][:40] == ids[:40][::-1]
    assert elapsed < 5


def test_module_level_on_science_is_one_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fix round B2: ``module_level=2`` on science is one ``setModuleLevel`` (expand rounds, one layout), not one
    layout per expand (7.7 s in the inventory). Counts layouts instead of timing them, so slow CI runners pass."""
    from alluvial.engine.diagram import Diagram

    calls = []
    update_layout = Diagram.update_layout
    monkeypatch.setattr(
        Diagram, "update_layout", lambda self, *a, **k: calls.append(1) or update_layout(self, *a, **k)
    )
    science = [str(DATA_DIR / f"science{y}_2y.stree") for y in (2001, 2003, 2005, 2007)]
    store = _store(science, colors=None, module_level=2)
    assert [len(n.visible_children) for n in store.diagram.children] == [429, 386, 352, 471]
    assert len(calls) == 2  # setNetworks, then the batched setModuleLevel
