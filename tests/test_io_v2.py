"""v2 IO: Infomap JSON input and multilayer layer splitting (docs/dev/port-notes/v2-io.md).

Parity with the TS fixtures' parsed inputs (``networks[i].file`` and ``leaves``), the reader's edge cases (§2.8, §3.4,
§3.5) and the Infomap-object path against the files Infomap writes.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import warnings
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from conftest import ALL_SCENARIOS, DATA_DIR, TESTS_DIR, load_fixture

import alluvial
from alluvial.io import NetworkFile, Node, read, read_file, split_layers
from alluvial.io.identifiers import calc_statistics
from alluvial.io.json_reader import parse_json
from alluvial.layout import _distinct_ids
from alluvial.tree_path import TreePath

ROOT = Path(__file__).resolve().parents[1]


def _quiet(fn, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return fn(*args, **kwargs)


# --- fixture parity -----------------------------------------------------------------------------------------


def _io_v2_scenarios() -> list[str]:
    return [
        s for s in ALL_SCENARIOS if {"json", "multilayerSplit"} & set(load_fixture(s).get("features") or ())
    ]


IO_V2_SCENARIOS = _io_v2_scenarios()


def _replay_inputs(inputs: dict[str, Any]) -> list[NetworkFile]:
    """Read each input file, split the listed ones and flatten, as documented in tools/ts-fixtures/README.md."""
    split = set(inputs.get("split") or ())
    parsed = [_quiet(read, TESTS_DIR / rel, identifier=inputs["identifier"]) for rel in inputs["files"]]
    out: list[NetworkFile] = []
    # the harness's file ids: stems, a repeated stem renamed `<stem>_<k>` (layout()'s rule)
    for i, (nf, input_id) in enumerate(zip(parsed, _distinct_ids([nf.id for nf in parsed]), strict=True)):
        nf.id = input_id
        if i in split:
            out.extend(_quiet(read, nf, identifier=inputs["identifier"], split_layers=True))
        else:
            out.append(nf)
    return out


def test_io_v2_scenarios_present() -> None:
    assert len(IO_V2_SCENARIOS) >= 14
    assert "mlayer-named-json__default" in IO_V2_SCENARIOS
    assert "planted-json__default" in IO_V2_SCENARIOS


@pytest.mark.parametrize("name", IO_V2_SCENARIOS)
def test_parsed_inputs_match_fixture(name: str) -> None:
    fx = load_fixture(name)
    inputs = fx["inputs"]
    files = _replay_inputs(inputs)
    assert len(files) == len(fx["networks"])
    sources = inputs.get("networkSources") or list(range(len(inputs["files"])))
    for i, (nf, net) in enumerate(zip(files, fx["networks"], strict=True)):
        assert nf.id == inputs["networkIds"][i]
        assert nf.name == inputs["networkNames"][i]
        assert nf.format == inputs["formats"][i]
        actual = {
            "path": inputs["files"][sources[i]],
            "format": nf.format,
            "numTopModules": nf.num_top_modules,
            "numLevels": nf.num_levels,
            "isStateNetwork": nf.is_state_network,
            "directed": nf.directed,
            "codelength": nf.codelength,
            "numNodes": len(nf.nodes),
        }
        if "layerId" in net["file"]:
            actual["layerId"] = nf.layer_id
            actual["originalId"] = nf.original_id
        assert actual == net["file"]
        identifiers = [n.identifier for n in nf.nodes]
        assert (len(set(identifiers)) == len(identifiers)) == net["identifiersUnique"]
        # Leaf rows: identifier, nodeId, stateId, moduleId (at the leaf's module level), insignificant.
        level = {(r[0], r[1], r[2]): r[4] for r in net["leaves"]}
        file_rows = sorted(
            (
                [
                    n.identifier,
                    n.id,
                    n.state_id,
                    TreePath(n.path).ancestor_at_level_as_string(
                        level.get((n.identifier, n.id, n.state_id), 1)
                    ),
                    not TreePath(n.path).is_significant(0),
                ]
                for n in nf.nodes
            ),
            key=repr,
        )
        engine_rows = sorted(([r[0], r[1], r[2], r[3], r[6]] for r in net["leaves"]), key=repr)
        assert file_rows == engine_rows


@pytest.mark.parametrize("name", ["planted-json__default", "mlayer-split-json__colorModuleIds"])
def test_json_modules_give_fixture_enter_exit_flow(name: str) -> None:
    from alluvial.engine.store import DiagramStore
    from alluvial.layout import LayoutOptions

    fx = load_fixture(name)
    files = _replay_inputs(fx["inputs"])
    store = DiagramStore(LayoutOptions.from_ts(fx["inputs"]["options"]))
    store.set_networks(files)
    for network, net in zip(store.diagram.children, fx["networks"], strict=True):
        expected = {m["id"]: (m["enterFlow"], m["exitFlow"]) for m in net["modules"]}
        actual = {m.id: (m.enter_flow, m.exit_flow) for m in network.modules_by_id.values()}
        assert actual == expected


# --- multilayer splitting -----------------------------------------------------------------------------------


def _ml_file(layer_ids: list[Any], *, layers: Any = None, id: str = "ml") -> NetworkFile:
    nodes = [
        Node(
            id=i + 1,
            flow=0.1,
            path=f"{i % 2 + 1}:{i + 1}",
            state_id=100 + i,
            layer_id=lid,
            identifier=f"s{i}",
        )
        for i, lid in enumerate(layer_ids)
    ]
    nf = NetworkFile(id=id, name=f"{id}.tree", format="tree", nodes=nodes, layers=layers, codelength=1.5)
    for key, value in calc_statistics(nodes).items():
        setattr(nf, key, value)
    return nf


def test_layer_order_is_js_object_key_order() -> None:
    # v2-io §2.3: array-index keys ascending, then the other keys in first-seen order.
    nf = _ml_file([2, 0, -1, 1.5, None, 10, 2], layers=[{"id": 2, "name": "Two"}])
    layers = split_layers(nf)
    assert [layer.layer_id for layer in layers] == [0, 2, 10, -1, 1.5, None]
    assert [layer.name for layer in layers] == [
        "Layer 0",
        "Two",
        "Layer 10",
        "Layer -1",
        "Layer 1.5",
        "Layer undefined",
    ]
    assert [layer.id for layer in layers] == [
        "ml_layer0",
        "ml_layer2",
        "ml_layer10",
        "ml_layer-1",
        "ml_layer1.5",
        "ml_layerundefined",
    ]
    assert [len(layer.nodes) for layer in layers] == [1, 2, 1, 1, 1, 1]
    # The "undefined" layer: calcStatistics says not multilayer, but the layer is expanded (§2.3).
    assert (
        layers[-1].is_multilayer is False and layers[-1].num_layers is None and layers[-1].is_expanded is True
    )
    assert all(layer.original_id == "ml" and layer.is_expanded for layer in layers)


def test_layer_names_use_strict_equality() -> None:
    layers = [
        {"id": "0", "name": "string zero"},
        {"id": True, "name": "true"},
        {"id": 2, "name": None},
        {"id": 2, "name": "second two"},
        {"id": 3, "name": "Three"},
        {"id": 3, "name": "shadowed"},
        "not an object",
    ]
    out = split_layers(_ml_file([0, 1, 2, 3], layers=layers))
    # "0" !== 0, true !== 1, the first match with a null name falls back, the first match wins.
    assert [layer.name for layer in out] == ["Layer 0", "Layer 1", "Layer 2", "Three"]


def test_layer_keys_collide_like_js() -> None:
    # String(-0) == String(0) and String("1") == String(1): one layer each, keeping the first node's value.
    out = split_layers(_ml_file([-0.0, 0, "1", 1]))
    assert [(layer.layer_id, len(layer.nodes)) for layer in out] == [(-0.0, 2), ("1", 2)]
    assert [layer.id for layer in out] == ["ml_layer0", "ml_layer1"]


def test_split_copies_fields_and_recomputes_statistics() -> None:
    nf = _ml_file([3, 1, 3, 1, 3])
    nf.version = "v2.15.1"
    out = split_layers(nf)
    assert [layer.layer_id for layer in out] == [1, 3]
    for layer in out:
        assert layer.version == "v2.15.1" and layer.codelength == 1.5 and layer.format == "tree"
        assert layer.num_layers == 1 and layer.is_multilayer is True
        stats = calc_statistics(layer.nodes)
        assert layer.flow_distribution == stats["flow_distribution"]
        assert layer.num_top_modules == stats["num_top_modules"]
    # File order inside each layer; identifiers are physical ids.
    assert [n.id for n in out[1].nodes] == [1, 3, 5]
    assert [n.identifier for n in out[1].nodes] == ["1", "3", "5"]


def test_split_does_not_mutate_input() -> None:
    nf = _ml_file([1, 2, 1])
    before = dataclasses.asdict(nf)
    out = split_layers(nf)
    assert dataclasses.asdict(nf) == before
    assert all(n is not m for layer in out for n in layer.nodes for m in nf.nodes)


def test_single_layer_and_custom_id_format() -> None:
    out = split_layers(_ml_file([7, 7]), id_format="{id}:{layer}")
    assert [layer.id for layer in out] == ["ml:7"]
    assert out[0].name == "Layer 7"


def test_split_non_multilayer_raises() -> None:
    nf = _quiet(read, DATA_DIR / "planted_t0.tree")
    with pytest.raises(ValueError, match="not multilayer"):
        split_layers(nf)
    with pytest.raises(ValueError, match="states=True"):
        read(DATA_DIR / "mlayer_flat.tree", split_layers=True)


def test_split_bad_layers_field_raises() -> None:
    with pytest.raises(ValueError, match="layers"):
        split_layers(_ml_file([1], layers={"id": 1}))
    # TS `layers.find((l) => l.id === layerId)` throws on a null entry it reaches, not on one after the match
    with pytest.raises(ValueError, match="null entry"):
        split_layers(_ml_file([1], layers=[None, {"id": 1, "name": "one"}]))
    assert split_layers(_ml_file([1], layers=[{"id": 1, "name": "one"}, None]))[0].name == "one"


def test_read_split_layers_paths_and_networkfile() -> None:
    from_path = _quiet(read, DATA_DIR / "mlayer_states.tree", split_layers=True)
    assert [layer.id for layer in from_path] == [f"mlayer_states_layer{k}" for k in (1, 2, 3, 4)]
    nf = _quiet(read, DATA_DIR / "mlayer_states.tree")
    from_nf = _quiet(read, nf, split_layers=True)
    assert [dataclasses.asdict(a) for a in from_nf] == [dataclasses.asdict(b) for b in from_path]
    assert _quiet(read, nf) is nf
    custom = _quiet(read, DATA_DIR / "mlayer_states.tree", network_id="m", split_layers=True)
    assert [layer.id for layer in custom] == ["m_layer1", "m_layer2", "m_layer3", "m_layer4"]


def test_split_ignores_identifier_mode_with_warning() -> None:
    with pytest.warns(UserWarning, match="ignored with split_layers"):
        by_name = read(DATA_DIR / "mlayer_states.tree", identifier="name", split_layers=True)
    by_id = _quiet(read, DATA_DIR / "mlayer_states.tree", split_layers=True)
    assert [[n.identifier for n in a.nodes] for a in by_name] == [
        [n.identifier for n in b.nodes] for b in by_id
    ]


def test_split_warns_duplicate_identifiers_per_layer() -> None:
    nf = _ml_file([1, 1, 2])
    nf.nodes[1].id = 1  # same physical node twice in layer 1
    with pytest.warns(UserWarning, match="shared by several nodes") as record:
        read(nf, split_layers=True)
    assert len([w for w in record if "shared by several" in str(w.message)]) == 1


def test_layout_of_split_layers() -> None:
    from alluvial import layout

    layers = _quiet(read, DATA_DIR / "mlayer_states.json", split_layers=True)
    geom = layout([*layers, _quiet(read, DATA_DIR / "mlayer_flat.tree")], colors="module_id")
    assert [n.id for n in geom.networks] == [*(layer.id for layer in layers), "mlayer_flat"]
    assert geom.streamlines


# --- Infomap objects ----------------------------------------------------------------------------------------


@cache
def _make_datasets():
    spec = importlib.util.spec_from_file_location(
        "make_datasets", ROOT / "tools/ts-fixtures/make_datasets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def _mlayer_infomap():
    pytest.importorskip("infomap")
    return _make_datasets().build_infomap("mlayer_states")


_SKIP = {
    "name",
    "filename",
    "size",
    "last_modified",
    "args",
    "started_at",
    "completed_in",
    "flow_model",
    "modules",
}


def _layer_view(nf: NetworkFile, *, skip: set[str] = _SKIP) -> dict[str, Any]:
    d = {f.name: getattr(nf, f.name) for f in dataclasses.fields(nf) if f.name not in skip}
    d["flow_distribution"] = list(nf.flow_distribution.items())
    d["nodes"] = [
        (n.identifier, n.id, n.state_id, n.layer_id, n.flow, str(TreePath(n.path)), n.name) for n in nf.nodes
    ]
    return d


def _assert_layers_equal(
    actual: list[NetworkFile], expected: list[NetworkFile], skip: set[str] = _SKIP
) -> None:
    assert [a.name for a in actual] == [e.name for e in expected]
    assert [_layer_view(a, skip=skip) for a in actual] == [_layer_view(e, skip=skip) for e in expected]


def test_infomap_object_split_equals_written_files(tmp_path: Path) -> None:
    im = _mlayer_infomap()
    tree, js = tmp_path / "mlayer_states.tree", tmp_path / "mlayer_states.json"
    im.write_tree(str(tree), states=True)
    im.write_json(str(js), states=True)
    from_object = _quiet(read, im, network_id="mlayer_states", split_layers=True)
    from_tree = _quiet(read, tree, split_layers=True)
    from_json = _quiet(read, js, split_layers=True)
    assert len(from_object) >= 2
    _assert_layers_equal(from_object, from_tree)
    # JSON: full-precision codelength, its own header fields and the format differ; nodes and statistics agree.
    json_skip = _SKIP | {
        "codelength",
        "format",
        "version",
        "relative_codelength_savings",
        "directed",
        "higher_order",
        "raw_modules",
    }
    _assert_layers_equal(from_json, from_tree, skip=json_skip)


def test_infomap_object_split_equals_committed_files() -> None:
    im = _mlayer_infomap()
    committed = _quiet(read, DATA_DIR / "mlayer_states.tree", split_layers=True)
    if float(f"{im._result.codelength:g}") != committed[0].codelength:
        pytest.skip("the installed infomap finds a different partition than the one that wrote tests/data")
    from_object = _quiet(read, im, network_id="mlayer_states", split_layers=True)
    _assert_layers_equal(from_object, committed)


def test_infomap_object_physical_level_cannot_split() -> None:
    im = _mlayer_infomap()
    with pytest.raises(ValueError, match="not multilayer"):
        read(im, states=False, split_layers=True)


# --- Infomap JSON reader ------------------------------------------------------------------------------------


def _write(tmp_path: Path, data: Any, name: str = "net.json") -> Path:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _node(**kw: Any) -> dict[str, Any]:
    return {"path": [1, 1], "flow": 0.5, "name": "a", "id": 1, **kw}


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ("not json", "not valid JSON"),
        ('{"nodes": [{"path": [1], "flow": NaN, "id": 1}]}', "not valid JSON"),
        ('{"nodes": [{"path": [1], "flow": Infinity, "id": 1}]}', "not valid JSON"),
        ("null", "expected a JSON object"),
        ("[]", "expected a JSON object"),
        ("1", "expected a JSON object"),
        ("{}", "no `nodes` list"),
        ('{"nodes": {}}', "not a list"),
        ('{"nodes": []}', "no nodes"),
        ('{"nodes": [{"flow": 1, "id": 1}]}', "no `path`"),
        ('{"nodes": [{"path": [1], "flow": 1}]}', "no numeric `id`"),
        ('{"nodes": [{"path": [1], "id": 1}]}', "no numeric `flow`"),
        (
            '{"nodes": [{"id": 1, "name": "a"}], "links": [{"source": 1, "target": 1}]}',
            "Infomap input network",
        ),
        ('{"version": "0.3.0", "networks": [{"nodes": []}], "state": {}}', "2019 saved-diagram format"),
        ('{"nodes": [{"path": [1], "flow": 1, "id": 1}], "modules": {}}', "`modules` must be a list"),
        ('{"nodes": [{"path": [1], "flow": 1, "id": 1}], "modules": [{"enterFlow": 0}]}', "module 0"),
    ],
)
def test_json_rejections(tmp_path: Path, content: str, match: str) -> None:
    path = _write(tmp_path, content)
    with pytest.raises(ValueError, match=match):
        read(path)


def test_json_rejections_from_dict() -> None:
    with pytest.raises(ValueError, match="2019 saved-diagram format is no longer supported"):
        read({"version": "0.3.0", "networks": []})
    with pytest.raises(ValueError, match="no `path`"):
        read({"nodes": [{"id": 1, "flow": 1}]})
    for flow in (math.nan, math.inf):  # a dict can hold what JSON text cannot
        with pytest.raises(ValueError, match="`flow` must be finite"):
            read({"nodes": [{"id": 1, "path": [1, 1], "flow": flow}]})
    with pytest.raises(TypeError, match="Infomap JSON dict"):
        read([1, 2])


def test_json_number_guards() -> None:
    assert parse_json("12345678901234567891") == 1.2345678901234567e19
    assert parse_json(str(2**53)) == 2**53 and isinstance(parse_json(str(2**53)), int)
    nf = read({"nodes": [_node(id=12345678901234567891)]})
    assert nf.nodes[0].identifier == "12345678901234567000"  # JS String of the rounded double


def test_json_bom_and_defaults(tmp_path: Path) -> None:
    path = tmp_path / "bom.json"
    path.write_text(json.dumps({"nodes": [_node()]}), encoding="utf-8-sig")
    nf = read(path)
    assert (nf.id, nf.name, nf.format, nf.filename) == ("bom", "bom.json", "json", "bom.json")
    # JSON top-level id/name come before the file defaults, explicit arguments before both.
    path = _write(
        tmp_path, {"id": "X", "name": "N", "format": "tree", "haveModules": False, "nodes": [_node()]}
    )
    nf = read(path)
    assert (nf.id, nf.name, nf.format, nf.have_modules) == ("X", "N", "json", True)
    assert nf.num_levels == 2  # statistics computed although the JSON says haveModules: false
    nf = read(path, network_id="I", name="M")
    assert (nf.id, nf.name) == ("I", "M")
    # dict sources: id falls back to the name, then to "network".
    assert (read({"nodes": [_node()]}).id, read({"nodes": [_node()]}).name) == ("network", "network")
    assert read({"nodes": [_node()]}, name="n").id == "n"
    assert read({"id": "J", "nodes": [_node()]}, name="n").id == "J"
    # TS spreads the JSON over its defaults: a number name is used (as a string), and so is "".
    assert read(_write(tmp_path, {"name": 5, "nodes": [_node()]})).name == "5"
    assert read(_write(tmp_path, {"name": "", "nodes": [_node()]})).name == ""
    assert read(_write(tmp_path, {"name": None, "nodes": [_node()]})).name.endswith(".json")
    assert (read({"name": "", "nodes": [_node()]}).name, read({"name": "", "nodes": [_node()]}).id) == (
        "",
        "network",
    )


def test_json_nodes_identifiers_and_paths() -> None:
    nodes = [
        _node(path=[1, 1], id=1, stateId=10, identifier="ID4"),
        _node(path="1:2", id=2, stateId=11, layerId=3, highlightIndex=2, moduleLevel=1, metadata={"0": "3"}),
        _node(path="2:1;3;", id=3, name="c", mec=0.1, modules=[2]),
    ]
    data = {"nodes": nodes, "directed": True, "codelength": 1.25, "flowModel": "directed", "stateLevel": True}
    snapshot = json.dumps(data)
    nf = read(data)
    assert json.dumps(data) == snapshot  # the input dict is not mutated
    n0, n1, n2 = nf.nodes
    assert [n.identifier for n in nf.nodes] == ["ID4", "11", "3"]  # a stored identifier wins over the mode
    assert n0.path == [1, 1] and n1.path == [1, 2]
    assert n2.path == "2:1;3;"  # P3: a `;` path stays a string (TreePath parses it), no [2, NaN]
    assert (n1.state_id, n1.layer_id, n1.highlight_index, n1.module_level, n1.metadata) == (
        11,
        3,
        2,
        1,
        {"0": "3"},
    )
    assert (nf.directed, nf.codelength, nf.flow_model, nf.state_level) == (True, 1.25, "directed", True)
    assert nf.is_state_network is True and nf.is_multilayer is False
    by_name = read(data, identifier="name")
    assert [n.identifier for n in by_name.nodes] == ["ID4", "a", "c"]


def test_json_insignificant_string_paths_give_no_nan_module() -> None:
    # P3/E3 (both engines; TS: parsers/parse-files.test.ts): stree-style string paths in Infomap JSON
    nodes = [_node(path="1;1;3;", id=1), _node(path="1:2;1;", id=2), _node(path="2:1", id=3)]
    nf = read({"nodes": nodes})
    assert [n.path for n in nf.nodes] == ["1;1;3;", "1:2;1;", [2, 1]]
    geom = alluvial.layout([{"nodes": nodes}])
    assert sorted(m.id for m in geom.networks[0].modules) == ["1", "2"]


def test_json_modules_map_to_infomap_modules() -> None:
    data = {
        "nodes": [_node()],
        "modules": [
            {"path": [0], "enterFlow": 0, "exitFlow": 0, "numEdges": 1, "numChildren": 1, "codelength": 0.2},
            {
                "path": [1],
                "enterFlow": 0.25,
                "exitFlow": 0.5,
                "links": [{"source": 1, "target": 2, "flow": 0.1}],
            },
        ],
    }
    nf = read(data)
    root, m1 = nf.modules
    assert (root.path, root.num_edges, root.num_children, root.links) == ([0], 1, 1, [])
    assert (m1.path, m1.enter_flow, m1.exit_flow) == ([1], 0.25, 0.5)
    assert [(link.source, link.target, link.flow) for link in m1.links] == [(1, 2, 0.1)]


def test_json_file_equals_dict_and_tree_of_same_run() -> None:
    path = DATA_DIR / "planted_t0.json"
    from_file = read(path)
    from_dict = read(json.loads(path.read_text()), network_id="planted_t0", name="planted_t0.json")
    skip = {"filename", "size", "last_modified"}
    assert {k: v for k, v in dataclasses.asdict(from_dict).items() if k not in skip} == {
        k: v for k, v in dataclasses.asdict(from_file).items() if k not in skip
    }
    tree = read_file(DATA_DIR / "planted_t0.tree")
    assert [(n.identifier, n.flow, str(TreePath(n.path)), n.name) for n in from_file.nodes] == [
        (n.identifier, n.flow, str(TreePath(n.path)), n.name) for n in tree.nodes
    ]
    assert list(from_file.flow_distribution.items()) == list(tree.flow_distribution.items())


def test_json_format_override(tmp_path: Path) -> None:
    path = _write(tmp_path, {"nodes": [_node()]}, name="net.txt")
    assert read_file(path, format="json").format == "json"
