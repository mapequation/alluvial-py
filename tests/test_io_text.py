"""Edge cases of the text parsers, identifiers and statistics (docs/dev/port-notes/parsers.md §2, §5, §6, §9)."""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import pytest

from alluvial._jscompat import NAN
from alluvial.io import NetworkFile, ParseError, read, read_file
from alluvial.io.identifiers import calc_statistics, set_identifiers
from alluvial.io.text import parse, parse_header, parse_node_header
from alluvial.io.types import Node

HEADER = "# v2.15.1\n# ./Infomap x\n# codelength 1.5 bits\n"


def _write(tmp_path: Path, name: str, text: str, *, encoding: str = "utf-8") -> Path:
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return p


def _nodes(text: str) -> list[Node]:
    return parse(text)[1]["nodes"]


# --- node header ---------------------------------------------------------------------------------------------


def test_node_header_comment_variants() -> None:
    assert parse_node_header(["#path flow name node_id"]) == ["path", "flow", "name", "node_id"]
    assert parse_node_header(["# x", "#   state_id module flow node_id"]) == [
        "state_id",
        "module",
        "flow",
        "node_id",
    ]
    assert parse_node_header(["# path flow  name node_id"]) == ["path", "flow", "", "name", "node_id"]


@pytest.mark.parametrize(
    ("line", "header"),
    [
        ('1:1 0.5 "a" 1', ["path", "flow", "name", "node_id"]),
        ('1:1 0.5 "a" 3 1', ["path", "flow", "name", "state_id", "node_id"]),
        ('1:1 0.5 "a" 3 1 2', ["path", "flow", "name", "state_id", "node_id", "layer_id"]),
        ('1:1:1: 0.5 "a" 1', ["path", "flow", "name", "node_id"]),
        ("1 1 0.5", ["node_id", "module", "flow"]),
        ("3 1 0.5 1", ["state_id", "module", "flow", "node_id"]),
        ("3 1 0.5 1 2", ["state_id", "module", "flow", "node_id", "layer_id"]),
    ],
)
def test_headerless_inference(line: str, header: list[str]) -> None:
    assert parse_node_header(["# v1", line]) == header


@pytest.mark.parametrize(
    "lines",
    [
        ['1;1; 0.5 "a" 1'],  # headerless stree with `;`
        ['1:1 0.5 "a" 1 2 3 4'],
        ["1 2"],
        ["a b c"],
        [""],  # an empty first non-# line
        ["# only", "# comments"],
    ],
)
def test_headerless_rejected(lines: list[str]) -> None:
    with pytest.raises(ParseError):
        parse_node_header(lines)


def test_dispatch_rejects_unknown_header() -> None:
    with pytest.raises(ParseError, match="tree or a clu"):
        parse("# path module flow\n1 1 0.5\n")
    with pytest.raises(ParseError, match="tree or a clu"):
        parse("# path flow node_id\n1 0.5 1\n")


# --- header ----------------------------------------------------------------------------------------------------


def test_parse_header_fields() -> None:
    text = (
        "# v2.15.1\n# ./Infomap net.net out\n# started at 2024-01-01 10:00:00\n# completed in 0.25 s\n"
        "# partitioned into 3 levels with 7 top modules\n# codelength 3.49842 bits\n"
        "# relative codelength savings 26.2781%\n# flow model undirdir\n# higher order\n# physical level\n"
        "# bipartite start id 12\n# module level -1\n# path flow name node_id\n"
    )
    h = parse_header(text.split("\n"))
    assert h == {
        "version": "v2.15.1",
        "args": "./Infomap net.net out",
        "started_at": "2024-01-01 10:00:00",
        "completed_in": 0.25,
        "num_levels": 3,
        "num_top_modules": 7,
        "codelength": 3.49842,
        "relative_codelength_savings": 26.2781 / 100,
        "flow_model": "undirdir",
        "state_level": False,
        "bipartite_start_id": 12,
        "higher_order": False,  # TS never sets it (no capture group)
    }
    assert parse_header(["# v1.7.3", "#path flow name node_id", "# module level 2"])["clu_level"] == 2
    assert parse_header(["# output/x", "#path flow name node_id"]) == {"higher_order": False}
    assert parse_header(["# v1", "# a", "x", "# codelength 1 bits"]) == {"args": "a", "higher_order": False}


# --- tree --------------------------------------------------------------------------------------------------------


def test_tree_names_and_tokens() -> None:
    text = (
        "# path flow name node_id\n"
        '1:1 0.25 "two words" 1\n'
        "1:2 0.25 abc 2\n"
        "1:3 0.25 'x' 3\n"
        '1:4\t0.125\t"it\'s"\t4\n'
        '2:1 0.125 "" 5\n'
        "short line\n"
        " \n"
    )
    nodes = _nodes(text)
    assert [n.name for n in nodes] == ["two words", "b", "", "it's", ""]
    assert [n.id for n in nodes] == [1, 2, 3, 4, 5]
    assert all(isinstance(n.id, int) for n in nodes)
    assert nodes[0].path == "1:1" and nodes[0].flow == 0.25


def test_tree_raw_paths_and_state_ids() -> None:
    nodes = _nodes(
        '# path flow name state_id node_id layer_id\n1:2;3; 0.5 "a" 0 7 2\n1;1:235; 0.5 "b" 1 7 3\n'
    )
    assert [n.path for n in nodes] == ["1:2;3;", "1;1:235;"]
    assert [(n.state_id, n.id, n.layer_id) for n in nodes] == [(0, 7, 2), (1, 7, 3)]


def test_tree_crlf_and_bom(tmp_path: Path) -> None:
    text = '# v2.15.1\r\n# x\r\n# path flow name node_id\r\n1:1 0.5 "a" 1\r\n1:2 0.5 "b" 2\r\n'
    nf = read_file(_write(tmp_path, "a.tree", "﻿" + text))
    assert nf.version == "v2.15.1"
    assert [(n.path, n.name, n.id) for n in nf.nodes] == [("1:1", "a", 1), ("1:2", "b", 2)]


def test_tree_nan_values_pass() -> None:
    nodes = _nodes('# path flow name node_id\n1:1 x "a" 1\n')
    assert math.isnan(nodes[0].flow)


def test_ftree_link_section() -> None:
    text = (
        "# path flow name node_id\n"
        '1:1 0.5 "a" 1\n'
        '1:2 0.5 "b" 2\n'
        "*Links directed\n"
        "#*Links path enterFlow exitFlow numEdges numChildren\n"
        "*Links root 0 0 1 1\n"
        "1 1 0.5\n"
        "\n"
        "*Links 1 0.25 0.5\n"
        "1 2\n"
        "2 1 0.25 9\n"
        "*Links 1:2 0.1 0.2 3 4 5\n"
    )
    _, contents = parse(text)
    assert contents["directed"] is True
    mods = contents["modules"]
    assert [m.path for m in mods] == [[0], [1], [1, 2]]
    assert (mods[0].enter_flow, mods[0].num_edges, mods[0].num_children) == (0, 1, 1)
    assert (mods[1].enter_flow, mods[1].exit_flow, mods[1].num_edges, mods[1].num_children) == (
        0.25,
        0.5,
        None,
        None,
    )
    assert [(lk.source, lk.target, lk.flow) for lk in mods[0].links] == [(1, 1, 0.5)]
    assert [(lk.source, lk.target, lk.flow) for lk in mods[1].links] == [(1, 2, None), (2, 1, 0.25)]
    assert mods[2].num_children == 4 and mods[2].links == []


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        ("", None),  # plain .tree: no directed/modules keys
        ("\n", (False, 0)),  # .tree ending in \n\n
        ("*Links undirected\n*Links root 0 0 1 1\n", (False, 1)),
        ("*Links undirdir\n", (False, 0)),
    ],
)
def test_ftree_link_section_presence(tail: str, expected) -> None:
    _, contents = parse('# path flow name node_id\n1:1 1 "a" 1\n' + tail)
    if expected is None:
        assert "directed" not in contents and "modules" not in contents
        return
    directed, num_modules = expected
    assert contents["directed"] is directed
    assert len(contents["modules"]) == num_modules


def test_blank_line_before_links_drops_modules() -> None:
    _, contents = parse('# path flow name node_id\n1:1 1 "a" 1\n\n*Links undirected\n*Links root 0 0 1 1\n')
    assert contents["directed"] is False and contents["modules"] == []


def test_bare_links_line_rejected() -> None:
    with pytest.raises(ParseError):
        parse('# path flow name node_id\n1:1 1 "a" 1\n*Links directed\n*Links\n')


# --- clu ---------------------------------------------------------------------------------------------------------


def test_clu_split_quirks() -> None:
    nodes = _nodes("# node_id module flow\n 1 1 0.5\n2\t1\t0.5\n3 2 0.5 \n4 2\n")
    assert [(n.id, n.module_id, n.flow) for n in nodes] == [(0, 1, 1.0), (3, 2, 0.5)]
    assert nodes[0].path is None and nodes[0].name is None


def test_clu_states(tmp_path: Path) -> None:
    text = "# v2.15.1\n# x\n# module level 1\n# state_id module flow node_id\n0 1 0.5 1\n5 2 0.5 1\n"
    nf = read_file(_write(tmp_path, "s.clu", text))
    assert nf.clu_level == 1
    assert [(n.path, n.identifier, n.name, n.state_id, n.id) for n in nf.nodes] == [
        ("1", "0", "1", 0, 1),
        ("2", "5", "1", 5, 1),
    ]
    assert nf.is_state_network and nf.num_levels == 1 and nf.num_top_modules == 2
    # clu ignores the identifier mode
    assert [n.identifier for n in read_file(tmp_path / "s.clu", identifier="name").nodes] == ["0", "5"]


# --- identifiers -------------------------------------------------------------------------------------------------


def test_set_identifiers_modes() -> None:
    def mk() -> list[Node]:
        return [
            Node(id=1, flow=0.5, path="1", name="a"),
            Node(id=2, flow=0.5, path="1", state_id=0, name=None),
            Node(id=1.5, flow=0.0, path="2", name="c"),
        ]

    nodes = mk()
    set_identifiers(nodes, "tree", "id")
    assert [n.identifier for n in nodes] == ["1", "0", "1.5"]
    nodes = mk()
    set_identifiers(nodes, "stree", "name")
    assert [n.identifier for n in nodes] == ["a", "0", "c"]
    nodes = mk()
    set_identifiers(nodes, "multilayer-expanded", "name")
    assert [n.identifier for n in nodes] == ["1", "2", "1.5"]
    nodes = mk()
    set_identifiers(nodes, "json", "id")
    assert [n.path for n in nodes] == [[1], [1], [2]]
    nodes = mk()
    set_identifiers(nodes, "net", "id")
    assert [n.identifier for n in nodes] == [None, None, None]


def test_identifier_name_mode_file(tmp_path: Path) -> None:
    p = _write(tmp_path, "n.tree", '# path flow name node_id\n1:1 0.5 "x" 1\n1:2 0.5 "y" 2\n')
    assert [n.identifier for n in read(p, identifier="name").nodes] == ["x", "y"]
    assert [n.identifier for n in read(p).nodes] == ["1", "2"]


# --- statistics --------------------------------------------------------------------------------------------------


def test_calc_statistics_quirks() -> None:
    nodes = [
        Node(id=1, flow=0.25, path="1:1:1:"),
        Node(id=2, flow=0.25, path="1:2;3;"),
        Node(id=3, flow=0.125, path="1;2;"),
        Node(id=4, flow=0.125, path="x:1"),
        Node(id=5, flow=0.25, path="2", layer_id=3),
    ]
    s = calc_statistics(nodes)
    assert s["num_levels"] == 3  # E1: the stree trailing ":" adds no level (was 4)
    assert s["num_top_modules"] == 3  # 1, NaN (counted once), 2
    keys = list(s["flow_distribution"])
    assert keys[:2] == [1, 2] and keys[2] is NAN
    assert s["flow_distribution"][1] == 0.5 and s["flow_distribution"][NAN] == 0.25
    assert s["is_multilayer"] is False and s["is_expanded"] is None and s["num_layers"] == 1
    assert s["is_state_network"] is False


def test_calc_statistics_nan_flow_resets() -> None:
    s = calc_statistics([Node(id=1, flow=math.nan, path="1"), Node(id=2, flow=0.5, path="1")])
    assert s["flow_distribution"] == {1: 0.5}


def test_calc_statistics_multilayer_and_empty() -> None:
    s = calc_statistics([Node(id=1, flow=1.0, path="1", state_id=0, layer_id=1)])
    assert s["is_multilayer"] is True and s["is_expanded"] is False and s["is_state_network"] is True
    with pytest.raises(ValueError):
        calc_statistics([])


# --- read() ------------------------------------------------------------------------------------------------------


def test_read_defaults(tmp_path: Path) -> None:
    p = _write(
        tmp_path, "my.net.ftree", HEADER + '# path flow name node_id\n1:1 1 "a" 1\n*Links undirected\n'
    )
    nf = read(p)
    assert (nf.id, nf.name, nf.filename, nf.format) == ("my.net", "my.net.ftree", "my.net.ftree", "ftree")
    assert nf.codelength == 1.5 and nf.directed is False and nf.modules == []
    nf = read(str(p), name="2020", network_id="y2020")
    assert (nf.id, nf.name) == ("y2020", "2020")
    assert read(nf) is nf


def test_read_uppercase_suffix(tmp_path: Path) -> None:
    p = _write(tmp_path, "A.TREE", '# path flow name node_id\n1:1 1 "a" 1\n')
    nf = read(p)
    assert nf.format == "tree" and nf.nodes[0].identifier == "1"


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("a.net", "*Vertices 1\n"),
        ("a.txt", '# path flow name node_id\n1:1 1 "a" 1\n'),
        ("a.tree", ""),  # empty file
        ("b.tree", "# path flow name node_id\n"),  # no node rows
        (
            "c.tree",
            '# path flow  name node_id\n1:1 1 "a" 1\n',
        ),  # double space shifts columns, all rows skipped
        ("a.clu", '# path flow name node_id\n1:1 1 "a" 1\n'),  # tree content in a .clu
        ("d.tree", "# node_id module flow\n1 1 1\n"),  # clu content in a .tree
    ],
)
def test_read_rejects(tmp_path: Path, name: str, text: str) -> None:
    with pytest.raises(ValueError):
        read(_write(tmp_path, name, text))


def test_read_argument_errors(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.tree", '# path flow name node_id\n1:1 1 "a" 1\n')
    with pytest.raises(ValueError, match="identifier"):
        read(p, identifier="label")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="states"):
        read(p, states=True)
    with pytest.raises(TypeError):
        read(42)


def test_duplicate_identifier_warning(tmp_path: Path) -> None:
    p = _write(tmp_path, "d.tree", '# path flow name node_id\n1:1 0.5 "a" 1\n2:1 0.5 "a" 1\n')
    with pytest.warns(UserWarning, match="identifier"):
        nf = read(p)
    assert len(nf.nodes) == 2
    assert isinstance(nf, NetworkFile)
    unique = _write(tmp_path, "u.tree", '# path flow name node_id\n1:1 0.5 "a" 1\n2:1 0.5 "a" 2\n')
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        read(unique)
    with pytest.warns(UserWarning, match="identifier"):
        read(unique, identifier="name")


def test_state_id_zero_identifier(tmp_path: Path) -> None:
    p = _write(tmp_path, "z.tree", '# path flow name state_id node_id\n1:1 1 "a" 0 4\n')
    assert read(p).nodes[0].identifier == "0"
