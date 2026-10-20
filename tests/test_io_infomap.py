"""The Infomap-object reader equals reading the files Infomap writes from the same object."""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import math
import warnings
from functools import cache
from pathlib import Path

import pytest
from conftest import DATA_DIR

infomap = pytest.importorskip("infomap")

from alluvial.io import NetworkFile, read, read_file
from alluvial.io.infomap_reader import from_infomap

ROOT = Path(__file__).resolve().parents[1]
DATASETS = json.loads((DATA_DIR / "datasets.json").read_text())["datasets"]
STEMS = sorted(DATASETS)
# Bookkeeping, UI-only and unported fields (parsers.md §11.2).
SKIP = {
    "id",
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


@cache
def _make_datasets():
    spec = importlib.util.spec_from_file_location(
        "make_datasets", ROOT / "tools/ts-fixtures/make_datasets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def _infomap(stem: str):
    return _make_datasets().build_infomap(stem)


def _comparable(nf: NetworkFile) -> dict:
    d = {f.name: getattr(nf, f.name) for f in dataclasses.fields(nf) if f.name not in SKIP}
    d["nodes"] = [dataclasses.asdict(n) for n in nf.nodes]
    return d


def _assert_same(actual: NetworkFile, expected: NetworkFile) -> None:
    a, e = _comparable(actual), _comparable(expected)
    assert a.keys() == e.keys()
    for key in e:
        if key == "nodes":
            assert len(a[key]) == len(e[key])
            for i, (x, y) in enumerate(zip(a[key], e[key], strict=True)):
                assert x == y, f"node {i}: {x} != {y}"
        elif key == "flow_distribution":
            assert list(a[key].items()) == list(e[key].items())
        else:
            assert a[key] == e[key], key


def _quiet(fn, *args, **kwargs):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return fn(*args, **kwargs)


@pytest.mark.parametrize("identifier", ["id", "name"])
@pytest.mark.parametrize("stem", STEMS)
def test_infomap_reader_equals_committed_files(stem: str, identifier: str) -> None:
    im = _infomap(stem)
    states = stem.startswith("states")
    committed = _quiet(read_file, DATA_DIR / DATASETS[stem]["files"][0])
    if float(f"{im._result.codelength:g}") != committed.codelength:
        pytest.skip(
            f"the installed infomap {infomap.__version__} finds a different partition for {stem} than the one that "
            "wrote tests/data (the reader itself is covered by test_infomap_reader_equals_written_files)"
        )
    for filename in DATASETS[stem]["files"]:
        fmt = filename.rsplit(".", 1)[1]
        expected = _quiet(read_file, DATA_DIR / filename, identifier=identifier)
        actual = from_infomap(im, format=fmt, states=states, identifier=identifier)
        _assert_same(actual, expected)


@pytest.mark.parametrize("states", [False, True])
@pytest.mark.parametrize("stem", ["states_t0", "planted_t0", "directed_t1", "multilevel_t0"])
def test_infomap_reader_equals_written_files(stem: str, states: bool, tmp_path: Path) -> None:
    im = _infomap(stem)
    result = im._result
    writers = {"tree": result.write_tree, "ftree": result.write_flow_tree, "clu": result.write_clu}
    for fmt, write in writers.items():
        path = tmp_path / f"{stem}{'_states' if states else ''}.{fmt}"
        write(str(path), states=states)
        for identifier in ("id", "name"):
            expected = _quiet(read_file, path, identifier=identifier)
            actual = from_infomap(result, format=fmt, states=states, identifier=identifier)
            _assert_same(actual, expected)


def test_clu_depth_level(tmp_path: Path) -> None:
    result = _infomap("multilevel_t0")._result
    for level in (2, -1):
        path = tmp_path / f"m{level}.clu"
        result.write_clu(str(path), depth_level=level)
        _assert_same(from_infomap(result, format="clu", clu_level=level), read_file(path))


def test_read_infomap_defaults() -> None:
    im = _infomap("states_t0")
    nf = read(im)
    assert (nf.name, nf.id, nf.format) == ("network", "network", "tree")
    assert nf.is_state_network and nf.state_level is True
    _assert_same(nf, read_file(DATA_DIR / "states_t0.tree"))
    nf = read(im, name="t0", network_id="a")
    assert (nf.name, nf.id) == ("t0", "a")
    assert read(_infomap("planted_t0")).is_state_network is False


def test_read_infomap_physical_view_warns_on_duplicates() -> None:
    im = infomap.Infomap(silent=True, seed=3, num_trials=2)
    for state_id, node_id in [(1, 1), (2, 2), (3, 2), (4, 3), (5, 4), (6, 1)]:
        im.add_state_node(state_id, node_id)
    im.add_links([(1, 2), (2, 1), (2, 6), (6, 1), (3, 4), (4, 5), (5, 3), (4, 3)])
    im.set_name(2, "two")
    im.run()
    nf = read(im)
    assert [n.identifier for n in nf.nodes] == ["1", "2", "6", "3", "4", "5"]
    assert [n.name for n in nf.nodes] == ["1", "two", "1", "two", "3", "4"]
    assert nf.codelength == 1.25786 and nf.relative_codelength_savings == 0.331943
    with pytest.warns(UserWarning, match="identifier"):
        phys = read(im, states=False)
    assert [(n.path, n.identifier, n.flow) for n in phys.nodes] == [
        ("1:1", "1", 0.3125),
        ("1:2", "2", 0.1875),
        ("2:1", "2", 0.1875),
        ("2:2", "3", 0.1875),
        ("2:3", "4", 0.125),
    ]
    assert phys.state_level is False


def test_exact_flows() -> None:
    result = _infomap("planted_t0")._result
    exact = from_infomap(result, exact=True)
    rounded = from_infomap(result)
    assert [n.flow for n in exact.nodes] == [n.flow for n in result.nodes()]
    assert all(
        math.isclose(a.flow, b.flow, rel_tol=1e-5) for a, b in zip(exact.nodes, rounded.nodes, strict=True)
    )
    assert exact.codelength == result.codelength


def test_unrun_infomap_rejected() -> None:
    with pytest.raises(ValueError, match="run"):
        read(infomap.Infomap(silent=True))


def test_bipartite_hidden_nodes(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        im = infomap.Infomap(silent=True, seed=11, num_trials=2, hide_bipartite_nodes=True)
    im.bipartite_start_id = 10
    for u in range(1, 7):
        for f in (10, 11) if u <= 3 else (12, 13):
            im.add_link(u, f)
    result = im.run()
    for fmt, write in (
        ("tree", result.write_tree),
        ("ftree", result.write_flow_tree),
        ("clu", result.write_clu),
    ):
        path = tmp_path / f"b.{fmt}"
        write(str(path))
        expected = read_file(path)
        _assert_same(from_infomap(im, format=fmt), expected)
        assert expected.bipartite_start_id == 10
    assert all(n.id < 10 for n in read_file(tmp_path / "b.tree").nodes)
    assert any(n.id >= 10 for n in read_file(tmp_path / "b.ftree").nodes)


def _blocks(nb: int = 3, size: int = 4) -> list[tuple[int, int]]:
    links = []
    for b in range(nb):
        ids = [1 + b * size + i for i in range(size)]
        links += [(i, j) for i in ids for j in ids if i < j]
        links.append((ids[0], 1 + ((b + 1) % nb) * size))
    return links


def _variant(kind: str):
    kwargs = {"two_level": {"two_level": True}, "trials": {"num_trials": 3}}.get(kind, {})
    if kind in ("directed", "undirdir", "outdirdir", "rawdir"):
        kwargs = {"flow_model": kind}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PendingDeprecationWarning)  # flow_model= on Infomap() (infomap 2.15)
        im = infomap.Infomap(silent=True, seed=1, **kwargs)
    im.add_links(_blocks())
    if kind == "isolated":
        im.add_node(100, "isolated")
        im.add_node(101)
    if kind == "names":
        for node, name in {
            1: "node one",
            2: "Göteborg å ä ö",
            3: "日本語",
            4: "tab\tsep",
            5: "#hash",
            6: "it's",
        }.items():
            im.set_name(node, name)
    if kind == "states":
        im = infomap.Infomap(silent=True, seed=1)
        for state, node in [(1, 1), (2, 2), (3, 3), (4, 2), (5, 4), (6, 5), (7, 4)]:
            im.add_state_node(state, node)
        im.add_links([(1, 2), (2, 3), (3, 1), (4, 5), (5, 6), (6, 7), (7, 4), (2, 5)])
    if kind == "multilayer":
        im = infomap.Infomap(silent=True, seed=1)
        for layer in (1, 2, 3):
            for s, t in _blocks(2, 3):
                im.add_multilayer_intra_link(layer, s + layer % 2, t)
        for node in range(1, 7):
            im.add_multilayer_inter_link(1, node, 2)
    im.run()
    return im


VARIANTS = ["undirected", "directed", "undirdir", "outdirdir", "rawdir", "two_level", "trials", "isolated", "names",
            "states", "multilayer"]  # fmt: skip


@pytest.mark.parametrize("kind", VARIANTS)
def test_realistic_variants_file_equals_object(kind: str, tmp_path: Path) -> None:
    im = _variant(kind)
    result = im._result
    for states in (False, True):
        for fmt, write in (
            ("tree", result.write_tree),
            ("ftree", result.write_flow_tree),
            ("clu", result.write_clu),
        ):
            path = tmp_path / f"{kind}{'_states' if states else ''}.{fmt}"
            write(str(path), states=states)
            for identifier in ("id", "name"):
                expected = _quiet(read_file, path, identifier=identifier)
                actual = _quiet(from_infomap, im, format=fmt, states=states, identifier=identifier)
                _assert_same(actual, expected)
                assert math.isclose(sum(n.flow for n in expected.nodes), 1, abs_tol=1e-5)
                assert expected.num_top_modules == result.num_top_modules


def test_multilayer_identifiers() -> None:
    # Infomap numbers multilayer state nodes itself (input order), so "id" gives run-dependent state ids, while
    # "name" gives the physical node (its id when unnamed); docs in alluvial.io.read.
    def build(links):
        im = infomap.Infomap(silent=True, seed=1)
        for a, b in links:
            im.add_multilayer_link(a, b)
        im.run()
        return im

    links = [((1, 1), (1, 2)), ((1, 2), (1, 3)), ((2, 1), (2, 3)), ((2, 3), (2, 2)), ((1, 1), (2, 1))]
    fwd, rev = build(links), build(links[::-1])
    state_ids = [{(n.layer_id, n.id): n.state_id for n in read(im).nodes} for im in (fwd, rev)]
    assert state_ids[0] != state_ids[1]
    nf = read(fwd)
    assert nf.is_state_network and nf.is_multilayer and nf.num_layers == 2
    with pytest.warns(UserWarning, match="identifier"):
        by_name = read(fwd, identifier="name")
    assert sorted(n.identifier for n in by_name.nodes) == ["1", "1", "2", "2", "3", "3"]
    assert [n.identifier for n in by_name.nodes] == [str(n.id) for n in by_name.nodes]


def test_names_with_spaces_and_unicode_round_trip(tmp_path: Path) -> None:
    im = _variant("names")
    path = tmp_path / "names.tree"
    im._result.write_tree(str(path))
    from_file = {n.id: n.identifier for n in read(path, identifier="name").nodes}
    from_obj = {n.id: n.identifier for n in read(im, identifier="name").nodes}
    assert from_file == from_obj
    assert from_obj[1] == "node one" and from_obj[3] == "日本語" and from_obj[7] == "7"


def test_quoted_name_reads_cleanly_from_object(tmp_path: Path) -> None:
    im = infomap.Infomap(silent=True, seed=1)
    im.add_links([(1, 2), (2, 3), (3, 1)])
    im.set_name(2, 'say "hi"')
    im.run()
    assert [n.name for n in read(im).nodes if n.id == 2] == ['say "hi"']
    path = tmp_path / "q.tree"
    im._result.write_tree(str(path))
    with pytest.warns(UserWarning, match="double quote"):
        read(path)


def test_installed_infomap_meets_lower_bound() -> None:
    from alluvial.io.infomap_reader import MIN_INFOMAP, _version_tuple

    assert _version_tuple(infomap.__version__) >= MIN_INFOMAP
    im = _variant("undirected")
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        warnings.simplefilter("error", PendingDeprecationWarning)
        warnings.simplefilter("error", FutureWarning)
        read(im)
        read(im, states=True)


@pytest.mark.skipif(not hasattr(infomap, "Network"), reason="infomap.run/Network arrived in infomap 2.15")
def test_functional_api_results() -> None:
    links = [(1, 2), (2, 3), (3, 1), (3, 4), (4, 5), (5, 4)]
    via_run = infomap.run(links, silent=True, seed=1)
    net = infomap.Network()
    net.add_links(links)
    with pytest.raises(TypeError, match=r"net\.run\(\)"):
        read(net)
    via_network = net.run(silent=True, seed=1)
    for result in (via_run, via_network):
        nf = read(result)
        assert len(nf.nodes) == 5 and nf.num_top_modules == result.num_top_modules
