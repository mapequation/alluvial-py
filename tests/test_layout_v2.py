"""v2 public API of ``layout``: ``module_level``, ``expand``, ``highlight``, ``colors="layer"|"physical_id"``,
``split_layers``, ``ids``. Parity: ``layout()`` with public arguments gives exactly the geometry of the TS fixture whose
store op sequence those arguments stand for (design.md "v2 design")."""

from __future__ import annotations

import dataclasses
import warnings
from typing import Any

import pytest
from conftest import DATA_DIR, V2_SCENARIOS, assert_matches, fixture_data_paths, load_fixture
from helpers_geometry import geometry_from_fixture
from test_engine_fixtures import read_fixture_inputs, replay_fixture
from test_geometry import _assert_geometry_equal

import alluvial
from alluvial import NodeInfo, layout, read
from alluvial.engine import DiagramStore
from alluvial.geometry import HighlightLabel, build_geometry
from alluvial.layout import LayoutOptions

_COLOR_OPS = {
    "colorMatchingModulesInAllNetworks": "similarity",
    "colorModuleIdsInAllNetworks": "module_id",
    "colorNodesInModulesInAllNetworks": "nodes",
    "colorByLayer": "layer",
    "colorByPhysicalId": "physical_id",
}


def layout_kwargs(fx: dict[str, Any]) -> dict[str, Any] | None:
    """The ``layout`` arguments that stand for the fixture's op sequence, or None if it has ops ``layout`` cannot
    express (or not in ``layout``'s order: expand, module level, color)."""
    inputs = fx["inputs"]
    if "initialOptions" in inputs:
        return None
    ops = inputs["operations"]
    macros = {m["atOperation"]: m for m in inputs.get("macros", ())}
    kwargs: dict[str, Any] = {"identifier": inputs["identifier"], "colors": None}
    split = set(inputs.get("split") or ())
    if split:
        kwargs["split_layers"] = [i in split for i in range(len(inputs["files"]))]
    stage = 0  # 0: expand, 1: module level, 2: color
    expand: list[tuple[int, str]] = []
    store = DiagramStore(LayoutOptions.from_ts(inputs["options"]))  # resolves index-addressed expands to ids
    store.set_networks(read_fixture_inputs(inputs))
    i = 1
    while i < len(ops):
        macro = macros.get(i)
        if macro is not None:
            op = macro["op"]
            if op["op"] == "moduleLevel" and stage <= 1:
                kwargs["module_level"] = op["levels"]
                stage = 2
            elif op["op"] == "highlight" and stage <= 2:
                kwargs["highlight"] = {label: ids for label, ids in op["groups"]}
                kwargs["highlight_colors"] = op["colors"]
                del kwargs["colors"]
                stage = 3
            else:
                return None
            for issued in ops[i : i + macro["numOperations"]]:
                store.apply(issued)
            i += macro["numOperations"]
            continue
        op = ops[i]
        if op["op"] == "expand" and stage == 0:
            network = store.diagram.children[op["networkIndex"]]
            module = (
                network.get_module(op["moduleId"])
                if "moduleId" in op
                else network.children[op["moduleIndex"]]
            )
            expand.append((op["networkIndex"], module.module_id))
        elif op["op"] in _COLOR_OPS and stage <= 2:
            kwargs["colors"] = _COLOR_OPS[op["op"]]
            stage = 3
        else:
            return None
        store.apply(op)
        i += 1
    if expand:
        kwargs["expand"] = expand
    return kwargs


EXPRESSIBLE = {s: kw for s in V2_SCENARIOS if (kw := layout_kwargs(load_fixture(s))) is not None}


def test_expressible_scenarios_cover_every_v2_layout_argument() -> None:
    # Guards the converter: these fixtures must be reproduced through layout() arguments alone.
    required = {
        "multilevel-tree__level2": {"module_level": 2},
        "multilevel-tree__level3": {"module_level": 3},
        "multilevel-tree__levelMixed": {"module_level": [1, 3, 2]},
        "multilevel-tree__level2Colored": {"module_level": 2, "colors": "similarity"},
        "debug5-stree__level3": {"module_level": 3},
        "science-stree__nameHighlight": {"identifier": "name"},
        "multilevel-tree__level2Highlight": {"module_level": 2},
        "multilevel-tree__expandThenHighlight": {"expand": [(0, "1")]},
        "multilevel-tree__expandColored": {"colors": "similarity"},
        "planted-ftree__highlight": {},
        "mlayer-unsplit__colorByLayer": {"colors": "layer"},
        "mlayer-unsplit__colorByPhysicalId": {"colors": "physical_id"},
        "states-tree__colorByPhysicalId": {"colors": "physical_id"},
        "mlayer-split__level2": {"module_level": 2},
        "mlayer-split__colored": {"colors": "similarity"},
        "mlayer-split-json__colorModuleIds": {"colors": "module_id"},
        "mlayer-split-twice__colorModuleIds": {"colors": "module_id", "split_layers": [True, True]},
    }
    for name, subset in required.items():
        assert name in EXPRESSIBLE, name
        for key, value in subset.items():
            assert EXPRESSIBLE[name][key] == value, (name, key)
    assert sum("highlight" in kw for kw in EXPRESSIBLE.values()) >= 6
    assert len(EXPRESSIBLE) >= 35


@pytest.mark.filterwarnings("ignore:identifier='name' is ignored with split_layers:UserWarning")
@pytest.mark.parametrize("name", sorted(EXPRESSIBLE))
def test_layout_reproduces_v2_fixture(name: str) -> None:
    fx = load_fixture(name)
    kwargs = EXPRESSIBLE[name]
    options = LayoutOptions.from_ts(fx["inputs"]["options"])
    geom = layout([str(p) for p in fixture_data_paths(fx)], **kwargs, **vars(options))
    _assert_geometry_equal(dataclasses.replace(geom, highlight_labels=()), geometry_from_fixture(fx))
    # Identical to building the geometry from the replayed store, the per-name highlight fields included.
    store, _, _ = replay_fixture(fx)
    expected = build_geometry(store.diagram, store.options, palette=tuple(store.highlight_colors))
    res = assert_matches(dataclasses.replace(geom, highlight_labels=()).to_dict(), expected.to_dict())
    assert res.non_bitwise == 0  # (NaN-aware, unlike ==)
    if "highlight" in kwargs:
        labels = list(kwargs["highlight"])
        assert geom.highlight_labels == tuple(
            HighlightLabel(label, store.get_highlight_index(c), c)
            for label, c in zip(labels, kwargs["highlight_colors"], strict=True)
        )
    else:
        assert geom.highlight_labels == ()


def test_module_level_one_and_no_expand_leave_v1_geometry() -> None:
    paths = [DATA_DIR / f"planted_t{i}.ftree" for i in range(3)]
    assert layout(paths, module_level=1, expand=[]) == layout(paths)
    assert layout(paths, module_level=[1, 1, 1]) == layout(paths)


def test_module_level_deeper_than_the_tree_stops() -> None:
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    assert layout(paths, module_level=9) == layout(paths, module_level=3)
    geom = layout(paths, module_level=3)
    assert max(m.level for n in geom.networks for m in n.modules) == 3
    assert all(n.outlines for n in geom.networks)


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (0, ValueError),
        (True, ValueError),
        ("2", ValueError),
        ([2, 2], ValueError),  # three networks
        ([2, 0, 2], ValueError),
    ],
)
def test_module_level_validation(value: Any, error: type) -> None:
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    with pytest.raises(error, match="module_level"):
        layout(paths, module_level=value)


def test_expand_by_network_id_and_validation() -> None:
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    by_index = layout(paths, expand=[(1, "1"), (1, "1:1")])
    assert layout(paths, expand=[("multilevel_t1", "1"), ("multilevel_t1", "1:1")]) == by_index
    assert {m.id for m in by_index.networks[1].modules} >= {"1:1:1", "1:2"}
    with pytest.raises(ValueError, match="no module '9'"):
        layout(paths, expand=[(0, "9")])
    with pytest.raises(ValueError, match="no network 'nope'"):
        layout(paths, expand=[("nope", "1")])
    with pytest.raises(TypeError, match="pairs"):
        layout(paths, expand=[(0, 1)])
    with pytest.raises(ValueError, match="cannot expand module '1'"):
        layout([DATA_DIR / "planted_t0.ftree"], expand=[(0, "1")])  # two-level tree: nothing to expand


def test_expand_missing_module_hints() -> None:
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    with pytest.raises(ValueError, match="expand its parent module '1' first"):
        layout(paths, expand=[(1, "1:1")])  # the sub-module exists, but its parent is not expanded
    with pytest.raises(ValueError, match="already expanded"):
        layout(paths, expand=[(1, "1"), (1, "1")])
    with pytest.raises(ValueError, match=r"no module '1:9' in network 'multilevel_t1'$"):
        layout(paths, expand=[(1, "1"), (1, "1:9")])  # no such sub-module: no hint


def test_module_level_accepts_numpy() -> None:
    np = pytest.importorskip("numpy")
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    expected = layout(paths, module_level=[2, 1, 3])
    assert layout(paths, module_level=np.array([2, 1, 3])) == expected
    assert layout(paths, module_level=(np.int64(2), 1, 3)) == expected
    assert layout(paths, module_level=np.int64(2)) == layout(paths, module_level=2)


# --------------------------------------------------------------------------------------------------- highlight

PLANTED = [DATA_DIR / f"planted_t{i}.ftree" for i in range(3)]


def test_highlight_mapping_normalizes_identifiers_and_keeps_label_order() -> None:
    by_int = layout(PLANTED, highlight={"b": [40, 41.0], "a": range(5, 10)})
    by_str = layout(PLANTED, highlight={"b": ["40", "41"], "a": [str(i) for i in range(5, 10)]})
    assert by_int == by_str
    assert [h.label for h in by_int.highlight_labels] == ["b", "a"]
    assert [h.highlight_index for h in by_int.highlight_labels] == [0, 1]
    assert by_int.palette[:2] == tuple(h.color for h in by_int.highlight_labels)


def test_highlight_callable_equals_the_mapping() -> None:
    groups = {"x": {str(i) for i in range(5, 21)}, "y": {str(i) for i in range(40, 56)}}
    seen: list[NodeInfo] = []

    def label(node: NodeInfo) -> str | None:
        seen.append(node)
        return next((k for k, ids in groups.items() if node.identifier in ids), None)

    geom = layout(PLANTED, highlight=label)
    assert geom == layout(PLANTED, highlight={k: sorted(v, key=int) for k, v in groups.items()})
    n_nodes = sum(len(read(p).nodes) for p in PLANTED)
    assert len(seen) == n_nodes  # once per node
    assert [n.network_index for n in seen] == sorted(n.network_index for n in seen)
    node = seen[0]
    assert node.network_id == "planted_t0" and isinstance(node.flow, float) and ":" in node.path
    with pytest.raises(TypeError):
        node.metadata["x"] = 1  # type: ignore[index]  # None or read-only


def test_highlight_callable_label_order_is_first_appearance() -> None:
    geom = layout(PLANTED, highlight=lambda n: "odd" if int(n.identifier) % 2 else "even")
    first = read(PLANTED[0]).nodes[0]
    expected = ["odd", "even"] if int(first.identifier) % 2 else ["even", "odd"]
    assert [h.label for h in geom.highlight_labels] == expected


def test_highlight_validation_and_warnings() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        layout(PLANTED, highlight={"a": [1]}, colors="similarity")
    with pytest.raises(ValueError, match="mutually exclusive"):
        layout(PLANTED, highlight={"a": [1]}, colors=None)
    with pytest.raises(ValueError, match="highlight_colors requires highlight"):
        layout(PLANTED, highlight_colors=["red"])
    with pytest.raises(ValueError, match="two highlight labels"):
        layout(PLANTED, highlight={"a": [1, 2], "b": [2]})
    with pytest.raises(TypeError, match="identifiers must be strings or numbers"):
        layout(PLANTED, highlight={"a": [True]})
    with pytest.raises(TypeError, match="iterable of node identifiers"):
        layout(PLANTED, highlight={"a": "12"})
    with pytest.raises(ValueError, match="distinct as strings"):
        layout(
            PLANTED, highlight=lambda n: 1 if n.identifier == "1" else ("1" if n.identifier == "2" else None)
        )
    with pytest.raises(ValueError, match="no color for label"):
        layout(PLANTED, highlight={"a": [1], "b": [2]}, highlight_colors={"a": "red"})
    with pytest.warns(UserWarning, match="2 of 3 identifiers match no node"):
        layout(PLANTED, highlight={"a": [1, "nope", 10**6]})
    with pytest.warns(UserWarning, match="default color"):
        geom = layout(PLANTED, highlight={"a": [1], "b": [50]}, highlight_colors=["#b6b69f", "red"])
    assert [h.highlight_index for h in geom.highlight_labels] == [-1, 0]
    with pytest.warns(UserWarning, match="share a color"):
        geom = layout(PLANTED, highlight={"a": [1], "b": [50]}, highlight_colors=["red", "red"])
    assert [h.highlight_index for h in geom.highlight_labels] == [0, 0]


def test_highlight_colors_accept_mappings_and_rgb_tuples() -> None:
    geom = layout(PLANTED, highlight={"a": [1], "b": [50]}, highlight_colors={"b": (0, 0, 1), "a": "tab:red"})
    assert [h.color for h in geom.highlight_labels] == ["tab:red", "#0000ff"]
    assert geom.palette == ("tab:red", "#0000ff")


def test_highlight_does_not_mutate_inputs() -> None:
    files = [read(p) for p in PLANTED]
    before = [[dataclasses.replace(n) for n in f.nodes] for f in files]
    layout(files, highlight={"a": [1, 2, 3]})
    assert [f.nodes for f in files] == before


def test_highlight_on_hlskip_does_not_warn() -> None:
    paths = [DATA_DIR / f"hlskip_t{i}.tree" for i in range(3)]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        layout(paths, highlight={"a": [3, 4], "b": [1]}, highlight_colors=["#ff0000", "#0000ff"])


# ------------------------------------------------------------------------------------------------ color ops


def test_colors_layer_and_physical_id_need_higher_order_networks() -> None:
    with pytest.raises(ValueError, match="colors='layer' needs a multilayer network"):
        layout(PLANTED, colors="layer")
    with pytest.raises(ValueError, match="colors='physical_id' needs a state or multilayer"):
        layout(PLANTED, colors="physical_id")
    with pytest.raises(ValueError, match="colors must be one of"):
        layout(PLANTED, colors="rainbow")


# ---------------------------------------------------------------------------------------------- split / ids


def test_split_layers_matches_reading_the_layers() -> None:
    path = DATA_DIR / "mlayer_states.tree"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        layers = read(path, split_layers=True)
    geom = layout([path], split_layers=True)
    assert [n.id for n in geom.networks] == [f.id for f in layers]
    assert [n.name for n in geom.networks] == [f.name for f in layers]
    assert geom == layout(layers)
    renamed = layout([path], split_layers=True, names=[f"L{i}" for i in range(len(layers))])
    assert [n.name for n in renamed.networks] == [f"L{i}" for i in range(len(layers))]
    with pytest.raises(ValueError, match=f"got 1 names for {len(layers)} networks"):
        layout([path], split_layers=True, names=["x"])
    with pytest.raises(ValueError, match="split_layers must be a bool or one bool per network"):
        layout([path], split_layers=[True, False])


def test_split_layers_per_input_and_collisions() -> None:
    path = DATA_DIR / "mlayer_states.tree"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        n_layers = len(read(path, split_layers=True))
    geom = layout([path, path], split_layers=[True, False])
    assert len(geom.networks) == n_layers + 1
    twice = layout([path, path], split_layers=True)
    ids = [n.id for n in twice.networks]
    assert len(set(ids)) == len(ids) == 2 * n_layers
    # the second file gets the id mlayer_states_2 before splitting (as in the fixture harness), so its layers
    # have their own original_id and colors="module_id" takes the per-network branch, as in the web app
    assert ids[0] == "mlayer_states_layer1"
    assert ids[n_layers] == "mlayer_states_2_layer1"
    nf = read(path)
    assert layout([nf, nf], split_layers=True, colors="module_id") == layout(
        [path, path], split_layers=True, colors="module_id"
    )


def test_split_layers_rejects_a_first_order_network() -> None:
    with pytest.raises(ValueError, match="multilayer"):
        layout(PLANTED, split_layers=True)


def test_layout_accepts_json_dicts_and_rejects_a_single_dict() -> None:
    import json

    data = json.loads((DATA_DIR / "planted_t0.json").read_text())
    geom = layout([data, {**data, "name": "b"}])
    assert [(n.id, n.name) for n in geom.networks] == [("net0", "network 0"), ("b", "b")]
    with pytest.raises(TypeError, match="wrap a single network in a list"):
        layout(data)


def test_plot_routes_the_v2_keywords() -> None:
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    paths = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
    ax = alluvial.plot(paths, module_level=2, ids=["a", "b", "c"], hierarchy="outline")
    art = alluvial.get_artists(ax)
    assert [n.id for n in art.geometry.networks] == ["a", "b", "c"]
    assert art.outlines
    import matplotlib.pyplot as plt

    plt.close("all")


def test_layout_keywords_match_the_signature() -> None:
    import inspect

    from alluvial.layout import LAYOUT_KEYWORDS

    params = inspect.signature(layout).parameters
    assert set(LAYOUT_KEYWORDS) == {p for p, v in params.items() if v.kind is v.KEYWORD_ONLY}
