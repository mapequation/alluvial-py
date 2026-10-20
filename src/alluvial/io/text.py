"""Port of ``@mapequation/infomap-parser`` 1.0.2 (``src/index.ts``) for ``.tree``/``.ftree``/``.stree``/``.clu`` text.

Behaviour follows ``parse(text, undefined, parseLinks=true, strictHeader=false)`` as called by the web app
(docs/dev/port-notes/parsers.md §2), including its quirks: raw path strings, ``name[1:-1]`` slicing, ``split(" ")``
column handling, ``higher_order`` always ``False`` and ``None`` padding of short ftree link records.
"""

from __future__ import annotations

import math
import re
import warnings
from typing import Any, Literal

from .._jscompat import _JS_WS, js_number
from .._warnings import user_stacklevel
from .types import InfomapModule, Link, Node

__all__ = [
    "ParseError",
    "lines",
    "parse",
    "parse_clu",
    "parse_header",
    "parse_node_header",
    "parse_tree",
]

Kind = Literal["tree", "clu"]

_DOT = r"[^\n\r  ]"  # JS `.` without the s flag
# JS \s (WhiteSpace + LineTerminator); Python's \s differs (e.g. \x1c-\x1f, \x85 vs U+FEFF).
_JS_S = "\t\n\x0b\x0c\r    -     　﻿"
_TOKEN_RE = re.compile(rf"[^{_JS_S}\"']+|\"[^\"]*\"")
_NODE_HEADER_RE = re.compile(rf"#[{_JS_S}]*(path|node_id|state_id)")
_LINE_SPLIT_RE = re.compile(r"\r?\n")

_VERSION_RE = re.compile(r"# (v[0-9]+\.[0-9]+\.[0-9]+)")
_ARGS_RE = re.compile(rf"# ({_DOT}+)")
_STARTED_RE = re.compile(rf"# started at ({_DOT}+)")
_COMPLETED_RE = re.compile(rf"# completed in ({_DOT}+) s")
_PARTITIONED_RE = re.compile(r"# partitioned into ([0-9]+) levels with ([0-9]+) top modules")
_CODELENGTH_RE = re.compile(rf"# codelength ({_DOT}+) bits")
_SAVINGS_RE = re.compile(rf"# relative codelength savings ({_DOT}+)%")
_FLOW_MODEL_RE = re.compile(rf"# flow model ({_DOT}+)")
_MODULE_LEVEL_RE = re.compile(r"# module level ([0-9]+)")
_STATE_LEVEL_RE = re.compile(r"# (state|physical) level")
_BIPARTITE_RE = re.compile(r"# bipartite start id ([0-9]+)")

# node header column -> Node attribute (IP:80-88)
_COLUMN_MAP = {
    "node_id": "id",
    "module": "module_id",
    "flow": "flow",
    "name": "name",
    "state_id": "state_id",
    "layer_id": "layer_id",
    "path": "path",
}


class ParseError(ValueError):
    """The text is not a tree/ftree/stree/clu file the TS parser accepts."""


def _num(token: Any) -> int | float:
    """JS ``Number(token)``, returned as ``int`` when integral so ids print like JS."""
    v = js_number(token)
    if math.isfinite(v) and v.is_integer():
        return int(v)
    return v


def _is_numeric(tokens: list[str]) -> bool:
    return all(not math.isnan(js_number(t)) for t in tokens)


def lines(text: str) -> list[str]:
    """Split on ``\\r?\\n`` like the TS ``lines()`` (no other line terminators, no trimming)."""
    return _LINE_SPLIT_RE.split(text)


def parse_node_header(file_lines: list[str]) -> list[str]:
    """Port of ``parseNodeHeader`` (IP:340-445): the node column names.

    Raises
    ------
    ParseError
        If no header comment is found and the first data line cannot be classified.
    """
    for line in file_lines:
        if not line.startswith("#"):
            break
        if _NODE_HEADER_RE.match(line):
            return line[1:].strip(_JS_WS).split(" ")

    for line in file_lines:
        if line.startswith("#"):
            continue
        if '"' in line:
            match = _TOKEN_RE.findall(line)
            if not match:
                raise ParseError(f"Invalid node line: {line}")
            numeric = [t for k, t in enumerate(match) if k not in (0, 2)]
            if not (_is_numeric(numeric) and _is_numeric(match[0].split(":"))):
                raise ParseError(f"Invalid node line: {line}")
            if len(match) == 4:
                return ["path", "flow", "name", "node_id"]
            if len(match) == 5:
                return ["path", "flow", "name", "state_id", "node_id"]
            if len(match) == 6:
                return ["path", "flow", "name", "state_id", "node_id", "layer_id"]
            raise ParseError(f"Invalid node line: {line}")
        fields = line.split(" ")
        if not _is_numeric(fields):
            raise ParseError(f"Invalid node line: {line}")
        if len(fields) == 3:
            return ["node_id", "module", "flow"]
        if len(fields) == 4:
            return ["state_id", "module", "flow", "node_id"]
        if len(fields) == 5:
            return ["state_id", "module", "flow", "node_id", "layer_id"]
        raise ParseError(f"Invalid node line: {line}")

    raise ParseError("Could not parse node header")


def parse_header(file_lines: list[str]) -> dict[str, Any]:
    """Port of ``parseHeader(lines, strict=false)`` (IP:447-578) with ``NetworkFile`` field names."""
    result: dict[str, Any] = {}
    first = file_lines[0] if file_lines else ""
    m = _VERSION_RE.match(first) if first else None
    if m:
        result["version"] = m[1]
    second = file_lines[1] if len(file_lines) > 1 else ""
    m = _ARGS_RE.match(second) if second else None
    if m:
        result["args"] = m[1]

    for line in file_lines[2:]:
        if not line.startswith("#"):
            break
        if m := _STARTED_RE.match(line):
            result["started_at"] = m[1]
            continue
        if m := _COMPLETED_RE.match(line):
            result["completed_in"] = js_number(m[1])
            continue
        if m := _PARTITIONED_RE.match(line):
            result["num_levels"] = _num(m[1])
            result["num_top_modules"] = _num(m[2])
            continue
        if m := _CODELENGTH_RE.match(line):
            result["codelength"] = js_number(m[1])
            continue
        if m := _SAVINGS_RE.match(line):
            result["relative_codelength_savings"] = js_number(m[1]) / 100
            continue
        if m := _FLOW_MODEL_RE.match(line):
            result["flow_model"] = m[1]
            continue
        if m := _MODULE_LEVEL_RE.match(line):
            result["clu_level"] = _num(m[1])
            continue
        # `# higher order` has no capture group in TS, so it never sets higherOrder (IP:540-544)
        if m := _STATE_LEVEL_RE.match(line):
            result["state_level"] = m[1] == "state"
            continue
        if m := _BIPARTITE_RE.match(line):
            result["bipartite_start_id"] = _num(m[1])

    result["higher_order"] = False
    return result


def _node_section(file_lines: list[str]):
    for i, line in enumerate(file_lines):
        if line.startswith("#") or len(line) == 0:
            continue
        if line.startswith("*"):
            break
        yield i, line


def _new_node(attrs: dict[str, Any]) -> Node:
    return Node(
        id=attrs.get("id"),  # type: ignore[arg-type]
        flow=attrs.get("flow"),  # type: ignore[arg-type]
        path=attrs.get("path"),  # type: ignore[arg-type]
        state_id=attrs.get("state_id"),
        layer_id=attrs.get("layer_id"),
        name=attrs.get("name"),
        module_id=attrs.get("module_id"),
    )


def parse_clu(file_lines: list[str], node_header: list[str] | None = None) -> dict[str, Any]:
    """Port of ``parseClu`` (IP:90-156). Nodes get ``id``, ``module_id``, ``flow`` (+ state/layer ids), no path."""
    header = parse_header(file_lines)
    if node_header is None:
        node_header = parse_node_header(file_lines)
    nodes: list[Node] = []
    for i, line in _node_section(file_lines):
        fields = line.split(" ")
        if len(fields) < len(node_header):
            continue
        attrs: dict[str, Any] = {}
        for k, col in enumerate(node_header):
            key = _COLUMN_MAP.get(col)
            if key is not None:
                attrs[key] = js_number(fields[k]) if key == "flow" else _num(fields[k])
        if attrs.get("id") is None or attrs.get("module_id") is None or attrs.get("flow") is None:
            raise ParseError(f"Invalid node at line {i + 1}: {line}")
        nodes.append(_new_node(attrs))
    return {**header, "nodes": nodes}


def _num_or_none(token: str | None) -> int | float | None:
    return None if token is None else _num(token)


def _flow_or_none(token: str | None) -> float | None:
    return None if token is None else js_number(token)


def _pad(values: list[Any], n: int) -> list[Any]:
    return (values + [None] * n)[:n]


def parse_tree(file_lines: list[str], node_header: list[str] | None = None) -> dict[str, Any]:
    """Port of ``parseTree(..., parseLinks=true)`` (IP:158-302), including the ftree ``*Links`` section.

    ``directed`` and ``modules`` are present only when the file has lines after the node section.
    """
    header = parse_header(file_lines)
    if node_header is None:
        node_header = parse_node_header(file_lines)
    nodes: list[Node] = []
    line_no = 0
    for i, line in _node_section(file_lines):
        line_no = i
        match = _TOKEN_RE.findall(line)
        if len(match) < len(node_header):
            continue
        attrs: dict[str, Any] = {}
        for j, col in enumerate(node_header):
            if col == "path":
                attrs["path"] = match[j]
            elif col == "name":
                attrs["name"] = match[j][1:-1]
            elif col == "node_id":
                attrs["id"] = _num(match[j])
            elif col in ("state_id", "layer_id"):
                attrs[col] = _num(match[j])
            elif col == "flow":
                attrs["flow"] = js_number(match[j])
            else:
                warnings.warn(f"Unknown field {col}", UserWarning, stacklevel=user_stacklevel())
        if any(attrs.get(k) is None for k in ("path", "flow", "name", "id")):
            raise ParseError(f"Invalid node at line {i + 1}: {line}")
        nodes.append(_new_node(attrs))

    line_no += 1
    if len(file_lines) <= line_no + 1:
        return {**header, "nodes": nodes}

    link_header = file_lines[line_no]
    directed = False
    modules: list[InfomapModule] = []
    if link_header.startswith("*Links"):
        parts = link_header.strip(_JS_WS).split(" ")
        directed = len(parts) > 1 and parts[1] == "directed"
        module: InfomapModule | None = None
        for line in file_lines[line_no + 1 :]:
            if len(line) == 0:
                continue
            if line.startswith("*Links"):
                parts = line.split(" ")
                if len(parts) < 2:
                    raise ParseError(f"Invalid module line: {line}")
                module_id = parts[1]
                path = [0] if module_id == "root" else [_num(x) for x in module_id.split(":")]
                enter, exit_, edges, children = _pad(parts[2:], 4)
                enter_flow, exit_flow = _flow_or_none(enter), _flow_or_none(exit_)
                num_edges, num_children = _num_or_none(edges), _num_or_none(children)
                module = InfomapModule(
                    path=path,
                    enter_flow=enter_flow,
                    exit_flow=exit_flow,
                    num_edges=num_edges,
                    num_children=num_children,
                )
                modules.append(module)
                continue
            if module is None:
                continue
            source, target, flow = _pad(line.split(" "), 3)
            module.links.append(
                Link(source=_num_or_none(source), target=_num_or_none(target), flow=_flow_or_none(flow))  # type: ignore[arg-type]
            )
    return {**header, "directed": directed, "nodes": nodes, "modules": modules}


def parse(text: str | list[str]) -> tuple[Kind, dict[str, Any]]:
    """Port of ``parse(text, undefined, true, false)`` (IP:44-78).

    Returns
    -------
    kind : {"tree", "clu"}
        Which parser the node header selected.
    contents : dict
        Header fields (``NetworkFile`` names), ``nodes`` and, for ftree, ``directed``/``modules``.
    """
    file_lines = lines(text) if isinstance(text, str) else text
    h = parse_node_header(file_lines)
    if "module" in h:
        if h[0] in ("node_id", "state_id"):
            return "clu", parse_clu(file_lines, h)
    elif "path" in h and ((len(h) >= 2 and h[-2] in ("name", "state_id")) or h[-1] == "layer_id"):
        return "tree", parse_tree(file_lines, h)
    raise ParseError("File must be either a tree or a clu file")
