"""Load validation (fix round WP4: E9, P1, P2, E14, E18; Y3, Y13).

Mirrors ``packages/alluvial-diagram/src/parsers/parse-files.test.ts`` in the TS worktree: a NaN, infinite, missing or
``null`` flow is rejected at load, extensions are case-insensitive, zip metadata entries are skipped, and the engine
reads ``bipartiteStartId: null`` and invalid ``moduleLevel`` values as absent.
"""

from __future__ import annotations

import json
import math
import zipfile
from pathlib import Path

import numpy as np
import pytest

from alluvial import layout
from alluvial.engine.diagram import Diagram
from alluvial.io import NetworkFile, Node, read, read_file
from alluvial.io.identifiers import validate_network_nodes

DATA = Path(__file__).parent / "data"
TREE = '# path flow name node_id\n1:1 0.5 "a" 1\n1:2 0.25 "b" 2\n2:1 {flow} "c" 3\n'


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400", "abc"])
@pytest.mark.parametrize("suffix", ["tree", "ftree", "stree"])
def test_text_reader_rejects_a_non_finite_flow(tmp_path: Path, token: str, suffix: str) -> None:
    path = tmp_path / f"x.{suffix}"
    path.write_text(TREE.format(flow=token), encoding="utf-8")
    with pytest.raises(ValueError, match=rf"x\.{suffix}: node 3 has no finite flow"):
        read(path)


def test_clu_reader_rejects_a_nan_flow(tmp_path: Path) -> None:
    path = tmp_path / "x.clu"
    path.write_text("# node_id module flow\n1 1 0.5\n2 1 NaN\n", encoding="utf-8")
    with pytest.raises(ValueError, match="node 2 has no finite flow"):
        read(path)


def test_finite_oddities_still_load(tmp_path: Path) -> None:
    for token in ("-0.1", "-0", "0e0"):
        path = tmp_path / "x.tree"
        path.write_text(TREE.format(flow=token), encoding="utf-8")
        assert math.isfinite(read(path).nodes[2].flow)


def test_planted_nan_file_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"nan_t0\.tree: node 1 has no finite flow"):
        read(DATA / "nan_t0.tree")


@pytest.mark.parametrize(
    ("flow", "match"),
    [
        ("null", "`flow` must be a finite number, got null"),  # JSON.stringify(NaN); was read as 0 (Y13)
        ('"0.5"', "no numeric `flow`"),
        ("true", "no numeric `flow`"),
        (None, "no numeric `flow`"),  # missing
    ],
)
def test_json_reader_rejects_null_missing_and_non_numeric_flows(tmp_path: Path, flow, match: str) -> None:
    node = '{"path": [1, 1], "id": 1' + ("" if flow is None else f', "flow": {flow}') + "}"
    path = tmp_path / "x.json"
    path.write_text('{"nodes": [' + node + "]}", encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        read(path)


def test_engine_rejects_a_network_file_with_a_nan_flow() -> None:
    """TS ``Network.create`` validates too: files that bypass the parser (library callers) are checked."""
    nf = read(DATA / "planted_t0.ftree")
    nf.nodes[3].flow = math.nan
    with pytest.raises(ValueError, match="node 4 has no finite flow"):
        Diagram([nf])
    with pytest.raises(ValueError, match="node 4 has no finite flow"):
        layout([nf])


def test_validate_network_nodes() -> None:
    validate_network_nodes([Node(id=1, flow=0, path="1"), Node(id=2, flow=-0.0, path="1")])
    validate_network_nodes([])
    with pytest.raises(ValueError, match="node 2 has no finite flow \\(Infinity\\)"):
        validate_network_nodes([Node(id=1, flow=1, path="1"), Node(id=2, flow=math.inf, path="1")])
    with pytest.raises(ValueError, match="no finite flow \\(NaN\\)"):
        validate_network_nodes([Node(id=1, flow=math.nan, path="1")])
    with pytest.raises(ValueError, match="no finite flow \\(missing\\)"):
        validate_network_nodes([Node(id=1, flow=None, path="1")])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="no nodes"):
        validate_network_nodes(None)


def test_uppercase_extension_reads_like_lowercase(tmp_path: Path) -> None:
    """P1: the TS parser left identifiers undefined for ``x.TREE``; both now dispatch on the lower-cased suffix."""
    text = (DATA / "planted_t0.ftree").read_text(encoding="utf-8")
    upper = tmp_path / "x.FTREE"
    upper.write_text(text, encoding="utf-8")
    a, b = read(upper), read(DATA / "planted_t0.ftree")
    assert a.format == "ftree"
    assert [(n.identifier, n.path, n.flow) for n in a.nodes] == [
        (n.identifier, n.path, n.flow) for n in b.nodes
    ]


def test_net_file_is_not_a_partition(tmp_path: Path) -> None:
    """TS accepts ``.net`` (the web app runs Infomap on it, so the flow check skips it); Python cannot run Infomap on
    a file and says so."""
    path = tmp_path / "x.net"
    path.write_text('*Vertices 2\n1 "a"\n2 "b"\n*Edges 1\n1 2\n', encoding="utf-8")
    with pytest.raises(ValueError, match="run Infomap"):
        read(path)


def test_unknown_extension_is_rejected(tmp_path: Path) -> None:
    for name in ("x.txt", "x"):
        path = tmp_path / name
        path.write_text(TREE.format(flow="0.25"), encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported network file format"):
            read_file(path)


def test_zip_skips_metadata_entries_and_reads_uppercase_suffixes(tmp_path: Path) -> None:
    """P2: directories, ``__MACOSX/`` and ``._*`` entries are skipped silently; suffixes are case-insensitive."""
    path = tmp_path / "networks.ZIP"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("dir/", "")
        z.writestr("dir/a.TREE", TREE.format(flow="0.25"))
        z.writestr("__MACOSX/dir/._a.TREE", "binary")
        z.writestr("dir/._b.tree", "binary")
        z.writestr("b.Json", json.dumps({"nodes": [{"path": [1, 1], "flow": 1, "id": 1}]}))
    files = read(path)
    assert [nf.format for nf in files] == ["tree", "json"]
    assert [nf.name for nf in files] == ["dir/a.TREE", "b.Json"]


def test_zip_with_a_nan_flow_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "networks.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.tree", TREE.format(flow="0.25"))
        z.writestr("b.tree", TREE.format(flow="NaN"))
    with pytest.raises(ValueError, match=r"b\.tree: node 3 has no finite flow"):
        read(path)


@pytest.mark.parametrize(
    ("module_level", "expected"),
    [(None, 1), (0, 1), (-1, 1), (1.5, 1), (True, 1), ("2", 1), (1, 1), (2, 2), (2.0, 2)],
)
def test_module_level_must_be_an_integer_of_at_least_one(module_level, expected: int) -> None:
    """E18: TS kept negative levels (full path, ``insignificant``); now only integers >= 1 are used."""
    nodes = [{"path": [1, 1, 1], "flow": 0.5, "id": 1}, {"path": [1, 2, 1], "flow": 0.5, "id": 2}]
    if module_level is not None:
        nodes[0]["moduleLevel"] = module_level
    diagram = Diagram([read({"nodes": nodes})])
    leaf = next(diagram.children[0].leaf_nodes())
    assert leaf.module_level == expected
    assert type(leaf.module_level) is int


def test_bipartite_start_id_null_is_not_bipartite() -> None:
    """E14: ``bipartiteStartId: null`` (hand-made JSON) made the TS network bipartite and hid every node."""
    nf = read({"nodes": [{"path": [1, 1], "flow": 1, "id": 1}], "bipartiteStartId": None})
    network = Diagram([nf]).children[0]
    assert not network.is_bipartite
    nf = NetworkFile(id="b", name="b", format="json", nodes=nf.nodes, bipartite_start_id=1)
    assert Diagram([nf]).children[0].is_bipartite


@pytest.mark.parametrize(
    "flow", [np.int64(1), np.float32(0.5), np.float64(0.25)], ids=["int64", "float32", "float64"]
)
def test_numpy_flows_are_accepted(flow) -> None:
    """WP4 review: a hand-built file may carry NumPy scalar flows (``numbers.Real``), as ``layout`` accepts."""
    validate_network_nodes([Node(id=1, flow=flow, path=[1, 1])])


@pytest.mark.parametrize(
    "flow", [True, np.bool_(True), 10**400, "1"], ids=["bool", "np-bool", "huge-int", "str"]
)
def test_non_real_or_overflowing_flows_are_rejected(flow) -> None:
    with pytest.raises(ValueError, match="has no finite flow"):
        validate_network_nodes([Node(id=1, flow=flow, path=[1, 1])])
