"""Partitions without Infomap: plain dicts, alluvial.partition and long-format data frames."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import alluvial

DATA = Path(__file__).parent / "data"

NETS = [{"Ann": 1, "Bo": 1, "Cy": 2}, {"Ann": 1, "Bo": 2, "Cy": "2:1"}]


def _modules(geom):
    return [[(m.id, m.flow) for m in network.modules] for network in geom.networks]


# --- partition --------------------------------------------------------------------------------------------------


def test_module_values_int_path_and_tuple():
    nf = alluvial.partition({"a": 1, "b": "2:1", "c": (2, 2), "d": [3, 1, 4], "e": "01:2"})
    assert [n.path for n in nf.nodes] == ["1:1", "2:1:1", "2:2:1", "3:1:4:1", "1:2:1"]
    assert nf.num_top_modules == 3
    assert nf.num_levels == 4  # as a .tree file: the leaf index is the last level


def test_node_keys_names_and_ids():
    nf = alluvial.partition({"Ann": 1, 7: 2})
    assert [(n.id, n.name, n.identifier) for n in nf.nodes] == [(1, "Ann", "Ann"), (7, "7", "7")]


def test_uniform_flows():
    nf = alluvial.partition({"a": 1, "b": 1, "c": 2})
    assert [n.flow for n in nf.nodes] == [1 / 3] * 3
    assert nf.flow_distribution == pytest.approx({1: 2 / 3, 2: 1 / 3})


def test_given_flows_are_normalized():
    nf = alluvial.partition({"a": 1, "b": 1, "c": 2}, flows={"c": 2, "a": 1, "b": 1}, name="t")
    assert [n.flow for n in nf.nodes] == [0.25, 0.25, 0.5]
    assert (nf.name, nf.id) == ("t", "t")
    zero = alluvial.partition({"a": 1, "b": 2}, flows={"a": 0, "b": 5})
    assert [n.flow for n in zero.nodes] == [0.0, 1.0]


@pytest.mark.parametrize(
    ("modules", "flows", "match"),
    [
        ({"a": 1}, {"a": -1}, "non-negative finite"),
        ({"a": 1}, {"a": math.nan}, "non-negative finite"),
        ({"a": 1}, {"a": math.inf}, "non-negative finite"),
        ({"a": 1}, {"a": "1"}, "non-negative finite"),
        ({"a": 1}, {"a": 1, "z": 1}, "not in modules"),
        ({"a": 1, "b": 1}, {"a": 1}, "no flow for node 'b'"),
        ({"a": 1}, {"a": 0}, "sum to 0"),
        ({"a": 0}, None, "positive int"),
        ({"a": -1}, None, "positive int"),
        ({"a": 1.5}, None, "positive int"),
        ({"a": True}, None, "positive int"),
        ({"a": "x"}, None, "positive int"),
        ({"a": "1:"}, None, "positive int"),
        ({"a": ()}, None, "positive int"),
        ({"a": (1, 0)}, None, "positive int"),
        ({"a": None}, None, "positive int"),
        ({1.5: 1}, None, "str \\(name\\) or an int"),
        ({1: 1, "1": 2}, None, "same identifier"),
        ({}, None, "empty"),
    ],
)
def test_partition_errors(modules, flows, match):
    with pytest.raises(ValueError, match=match):
        alluvial.partition(modules, flows)


def test_partition_type_errors():
    with pytest.raises(TypeError, match="modules must be a mapping"):
        alluvial.partition([("a", 1)])
    with pytest.raises(TypeError, match="flows must be a mapping"):
        alluvial.partition({"a": 1}, [1])
    with pytest.raises(TypeError, match="name must be a string"):
        alluvial.partition({"a": 1}, name=2020)


# --- dicts and partitions in layout -----------------------------------------------------------------------------


def test_dict_networks_in_layout():
    geom = alluvial.layout(NETS, names=["2020", "2021"])
    assert [(n.name, n.id) for n in geom.networks] == [("2020", "net0"), ("2021", "net1")]
    # top modules: module 2 of 2021 holds Bo and Cy (its sub-module 2:1)
    assert _modules(geom) == [
        [("1", pytest.approx(2 / 3)), ("2", pytest.approx(1 / 3))],
        [("2", pytest.approx(2 / 3)), ("1", pytest.approx(1 / 3))],
    ]
    assert [n.name for n in alluvial.layout(NETS).networks] == ["network 0", "network 1"]


def test_matching_across_networks_by_key():
    geom = alluvial.layout([{"a": 1, "b": 1, "c": 2}, {"c": 1, "a": 2, "b": 2}])
    # every node changes module id, but a and b stay together and c stays alone: two streamlines
    assert sorted((s.left[1], s.right[1]) for s in geom.streamlines) == [("1", "2"), ("2", "1")]
    # no shared keys: no streamlines
    assert alluvial.layout([{"a": 1}, {"b": 1}]).streamlines == ()


def test_partition_names_and_ids():
    named = alluvial.partition({"a": 1}, name="2020")
    unnamed = alluvial.partition({"a": 1})
    geom = alluvial.layout([named, unnamed, {"a": 1}])
    assert [(n.name, n.id) for n in geom.networks] == [
        ("2020", "2020"),
        ("network 1", "net1"),
        ("network 2", "net2"),
    ]
    geom = alluvial.layout([named, named])
    assert [n.id for n in geom.networks] == ["2020", "2020_2"]


def test_flowless_defaults_to_nodes():
    geom = alluvial.layout(NETS)
    assert (geom.options.module_size, geom.options.sort_modules_by) == ("nodes", "nodes")
    geom = alluvial.layout([alluvial.partition(n) for n in NETS])
    assert (geom.options.module_size, geom.options.sort_modules_by) == ("nodes", "nodes")


def test_flowless_explicit_value_wins():
    geom = alluvial.layout(NETS, module_size="flow")
    assert (geom.options.module_size, geom.options.sort_modules_by) == ("flow", "nodes")
    geom = alluvial.layout(NETS, sort_modules_by="flow")
    assert (geom.options.module_size, geom.options.sort_modules_by) == ("nodes", "flow")


def test_mixed_flows_keep_flow_defaults():
    with_flows = alluvial.partition({"Ann": 1, "Bo": 2, "Cy": 2}, flows={"Ann": 1, "Bo": 1, "Cy": 1})
    for networks in ([NETS[0], with_flows], [NETS[0], DATA / "abcchain_t0.tree"]):
        geom = alluvial.layout(networks)
        assert (geom.options.module_size, geom.options.sort_modules_by) == ("flow", "flow")


def test_infomap_json_dict_still_read_as_json():
    path = DATA / "bipartite_t0.json"
    from_dict = alluvial.layout([json.loads(path.read_text())], ids=["x"], names=["x"])
    from_path = alluvial.layout([path], ids=["x"], names=["x"])
    assert from_dict == from_path
    assert from_dict.options.module_size == "flow"


def test_clu_equivalence(tmp_path):
    modules = [{1: 1, 2: 1, 3: 2, 4: 2, 5: 3}, {1: 1, 2: 2, 3: 2, 4: 2, 5: 1}]
    paths = []
    for i, network in enumerate(modules):
        rows = "".join(f"{node} {module} {1 / len(network)!r}\n" for node, module in network.items())
        path = tmp_path / f"t{i}.clu"
        path.write_text("# node_id module flow\n" + rows)
        paths.append(path)
    kwargs = {"names": ["a", "b"], "ids": ["a", "b"], "module_size": "nodes", "sort_modules_by": "nodes"}
    assert alluvial.layout(modules, **kwargs) == alluvial.layout(paths, **kwargs)
    # the flow-less dicts default to node counts
    assert alluvial.layout(modules, names=["a", "b"], ids=["a", "b"]) == alluvial.layout(paths, **kwargs)


def test_bad_dict_network():
    with pytest.raises(ValueError, match="positive int"):
        alluvial.layout([{"a": [1.5]}])


# --- data frames ------------------------------------------------------------------------------------------------


@pytest.fixture
def pd():
    return pytest.importorskip("pandas")


def test_dataframe_default_columns(pd):
    df = pd.DataFrame(
        {
            "network": ["2020"] * 3 + ["2021"] * 3,
            "node": ["Ann", "Bo", "Cy"] * 2,
            "module": [1, 1, 2, 1, 2, "2:1"],
        }
    )
    geom = alluvial.layout(df)
    assert geom == alluvial.layout(NETS, names=["2020", "2021"], ids=["2020", "2021"])
    assert geom.options.module_size == "nodes"
    assert [n.name for n in alluvial.layout([df]).networks] == ["2020", "2021"]


def test_dataframe_flow_column(pd):
    df = pd.DataFrame({"network": [1, 1, 2], "node": [10, 20, 10], "module": [1, 2, 1], "flow": [3, 1, 2]})
    nets = alluvial.from_dataframe(df)
    assert [(nf.name, [n.flow for n in nf.nodes]) for nf in nets] == [("1", [0.75, 0.25]), ("2", [1.0])]
    assert [n.id for n in nets[0].nodes] == [10, 20]
    assert alluvial.layout(df).options.module_size == "flow"


def test_dataframe_custom_columns(pd):
    df = pd.DataFrame(
        {"year": [2021, 2021, 2020], "who": ["a", "b", "a"], "comm": [(1, 2), 2, 1], "w": [1.0, 1.0, 5.0]}
    )
    nets = alluvial.from_dataframe(df, network="year", node="who", module="comm")
    assert [(nf.name, [n.path for n in nf.nodes]) for nf in nets] == [
        ("2021", ["1:2:1", "2:1"]),
        ("2020", ["1:1"]),
    ]
    assert all(n.flow == 0.5 for n in nets[0].nodes)
    weighted = alluvial.from_dataframe(df, network="year", node="who", module="comm", flow="w")
    assert [n.flow for n in weighted[0].nodes] == [0.5, 0.5]


def test_dataframe_categorical_order(pd):
    df = pd.DataFrame({"network": ["b", "a", "b", "a"], "node": [1, 1, 2, 2], "module": [1, 1, 1, 2]})
    df["network"] = pd.Categorical(df["network"], categories=["unused", "a", "b"], ordered=True)
    assert [nf.name for nf in alluvial.from_dataframe(df)] == ["a", "b"]
    assert [nf.name for nf in alluvial.from_dataframe(df.astype({"network": str}))] == ["b", "a"]


def test_dataframe_errors(pd):
    df = pd.DataFrame({"network": [1], "node": [1], "module": [1]})
    with pytest.raises(ValueError, match="no column\\(s\\) 'year'"):
        alluvial.from_dataframe(df, network="year")
    with pytest.raises(ValueError, match="'w'"):
        alluvial.from_dataframe(df, flow="w")
    with pytest.raises(ValueError, match="no column\\(s\\) 'module'"):
        alluvial.layout(df.rename(columns={"module": "m"}))
    with pytest.raises(ValueError, match="more than once"):
        alluvial.from_dataframe(pd.concat([df, df]))
    with pytest.raises(ValueError, match="no rows"):
        alluvial.from_dataframe(df.iloc[:0])
    with pytest.raises(TypeError, match="data frame"):
        alluvial.from_dataframe({"network": [1]})


def test_module_paths_make_sub_modules() -> None:
    """A path module like "1:2" is a sub-module that ``module_level=2`` shows, as in a .tree file."""
    nets = [{"a": "1:1", "b": "1:1", "c": "1:2", "d": 2}, {"a": "1:1", "b": "1:2", "c": "1:2", "d": 2}]
    top = alluvial.layout(nets)
    assert [sorted(m.path for m in n.modules) for n in top.networks] == [[(1,), (2,)], [(1,), (2,)]]
    sub = alluvial.layout(nets, module_level=2)
    assert [sorted(m.path for m in n.modules) for n in sub.networks] == [
        [(1, 1), (1, 2), (2,)],
        [(1, 1), (1, 2), (2,)],
    ]
