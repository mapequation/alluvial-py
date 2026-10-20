"""Infomap JSON output (``infomap -o json``, ``im.write_json``) -> ``NetworkFile``, like the web app loads it.

The TS path is ``JSON.parse`` -> ``setIdentifiers(nodes, "json", identifier)`` -> ``createFile`` (spec:
docs/dev/port-notes/v2-io.md §3). Python reads with JS number semantics (§3.5): ``NaN``/``Infinity`` tokens are
rejected, integers beyond 2**53 become doubles. Inputs the TS rejects are rejected with a ``ValueError`` (§3.4);
a node without ``flow`` is rejected too (TS would propagate NaN into the geometry).
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from .._jscompat import js_number_to_string
from .identifiers import create_file, set_identifiers
from .types import InfomapModule, Link, NetworkFile, Node

__all__ = ["from_json_dict", "parse_json", "read_json"]

_HOW_TO = (
    "write a partition with `infomap net.net out/ -o json` (or `-o tree`), im.write_json('net.json') or "
    "im.write_tree('net.tree'), or pass the infomap.Infomap object to alluvial.read"
)

#: The error for a 2019 saved diagram (top-level ``networks``, no ``nodes``), which is no longer read.
SAVED_DIAGRAM_2019 = "the 2019 saved-diagram format is no longer supported; use alluvial 0.4 to convert"

# JSON top-level key -> NetworkFile field. Other keys (numModules, numLevels, numTopModules, seed, trials, ...)
# are carried by TS but read by nothing; numLevels/numTopModules are recomputed by calcStatistics.
_FILE_KEYS = {
    "version": "version",
    "args": "args",
    "startedAt": "started_at",
    "completedIn": "completed_in",
    "codelength": "codelength",
    "relativeCodelengthSavings": "relative_codelength_savings",
    "flowModel": "flow_model",
    "higherOrder": "higher_order",
    "stateLevel": "state_level",
    "bipartiteStartId": "bipartite_start_id",
    "directed": "directed",
    "layers": "layers",
    "numTrials": "num_trials",
    "colors": "colors",
    "alluvial": "alluvial",
}

# JSON node key -> Node field (everything else, e.g. ``modules`` and ``mec``, is ignored as in the engine).
_NODE_KEYS = {
    "stateId": "state_id",
    "layerId": "layer_id",
    "name": "name",
    "identifier": "identifier",
    "highlightIndex": "highlight_index",
    "moduleLevel": "module_level",
    "metadata": "metadata",
    "color": "color",
}

_MAX_SAFE = 2**53


def _parse_int(s: str) -> int | float:
    # JS JSON.parse gives a double: integers beyond 2**53 lose precision exactly like this.
    v = int(s)
    return v if abs(v) <= _MAX_SAFE else float(s)


def _parse_constant(s: str) -> Any:
    raise ValueError(f"{s} is not valid JSON (JavaScript's JSON.parse rejects it)")


def parse_json(text: str) -> Any:
    """``JSON.parse`` with JS number semantics (v2-io §3.5). Raises ``ValueError`` for invalid JSON."""
    return json.loads(text, parse_int=_parse_int, parse_constant=_parse_constant)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _describe(where: str) -> str:
    return f"{where}: " if where else ""


def _check_top_level(data: Any, where: str) -> list[Any]:
    """Validate the parsed top level and return its ``nodes`` list (§3.4, §7.1 dispatch)."""
    pre = _describe(where)
    if not isinstance(data, dict):
        raise ValueError(
            f"{pre}expected a JSON object with Infomap output (`nodes` and `modules`), got "
            f"{'null' if data is None else type(data).__name__}; {_HOW_TO}"
        )
    nodes = data.get("nodes")
    if nodes is None:
        if "networks" in data:
            raise ValueError(f"{pre}{SAVED_DIAGRAM_2019}")
        raise ValueError(f"{pre}not Infomap JSON output: there is no `nodes` list; {_HOW_TO}")
    if not isinstance(nodes, list):
        raise ValueError(f"{pre}not Infomap JSON output: `nodes` is a {type(nodes).__name__}, not a list")
    if not nodes:
        raise ValueError(f"{pre}network has no nodes")
    first = nodes[0]
    if (
        isinstance(first, dict)
        and "path" not in first
        and any(k in data for k in ("links", "states", "intra", "inter"))
    ):
        raise ValueError(
            f"{pre}this is an Infomap input network (nodes without module paths); run Infomap on it first: {_HOW_TO}"
        )
    return nodes


def _node(raw: Any, index: int, pre: str) -> Node:
    if not isinstance(raw, dict):
        raise ValueError(f"{pre}node {index} is not a JSON object")
    path = raw.get("path")
    if path is None:
        raise ValueError(f"{pre}node {index} has no `path` (is this Infomap output?)")
    if not isinstance(path, (list, str)) and not _is_number(path):
        raise ValueError(
            f"{pre}node {index}: `path` must be a list, a string or a number, got {type(path).__name__}"
        )
    # a number is a top-level module (TS: TreePath.toArray(2) = [2], done by set_identifiers)
    node_id = raw.get("id")
    # TS needs `id` only for some identifier modes; Infomap always writes it, so it is required here.
    if not _is_number(node_id):
        raise ValueError(f"{pre}node {index} has no numeric `id`")
    flow = raw.get("flow")
    if flow is None and "flow" in raw:  # JSON.stringify writes a NaN/Infinity flow as null
        raise ValueError(f"{pre}node {index}: `flow` must be a finite number, got null")
    if not _is_number(flow):
        raise ValueError(f"{pre}node {index} has no numeric `flow`")
    if not math.isfinite(flow):  # only a dict can hold these: JSON has no NaN/Infinity
        raise ValueError(f"{pre}node {index}: `flow` must be finite, got {flow!r}")
    node = Node(id=node_id, flow=flow, path=path)
    for key, attr in _NODE_KEYS.items():
        value = raw.get(key)
        if value is not None:
            setattr(node, attr, value)
    return node


def _module(raw: Any, index: int, pre: str) -> InfomapModule:
    if not isinstance(raw, dict) or not isinstance(raw.get("path"), list):
        raise ValueError(f"{pre}module {index} has no `path` list")
    links = []
    for link in raw.get("links") or ():
        if not isinstance(link, dict):
            raise ValueError(f"{pre}module {index}: a link is not a JSON object")
        links.append(Link(source=link.get("source"), target=link.get("target"), flow=link.get("flow")))
    return InfomapModule(
        path=raw["path"],
        enter_flow=raw.get("enterFlow"),
        exit_flow=raw.get("exitFlow"),
        num_edges=raw.get("numEdges"),
        num_children=raw.get("numChildren"),
        links=links,
    )


def from_json_dict(
    data: Any,
    *,
    id: str,
    name: str,
    identifier: str = "id",
    filename: str | None = None,
    size: int = 0,
    last_modified: int = 0,
    where: str = "",
) -> NetworkFile:
    """Build a ``NetworkFile`` from parsed Infomap JSON (``setIdentifiers(…, "json")`` + ``createFile``).

    ``id`` and ``name`` are the final values (callers resolve the JSON ``id``/``name`` defaults). The input is not
    mutated. Raises ``ValueError`` for input the TS rejects (§3.4) and for nodes without ``flow``.
    """
    pre = _describe(where)
    raw_nodes = _check_top_level(data, where)
    nodes = [_node(raw, i, pre) for i, raw in enumerate(raw_nodes)]
    set_identifiers(nodes, "json", identifier)
    contents: dict[str, Any] = {"nodes": nodes}
    for key, attr in _FILE_KEYS.items():
        if data.get(key) is not None:
            contents[attr] = data[key]
    modules = data.get("modules")
    if modules is not None:
        if not isinstance(modules, list):
            raise ValueError(f"{pre}`modules` must be a list, got {type(modules).__name__}")
        contents["modules"] = [_module(m, i, pre) for i, m in enumerate(modules)]
        contents["raw_modules"] = modules
    return create_file(
        contents,
        format="json",
        id=id,
        name=name,
        filename=filename,
        size=size,
        last_modified=last_modified,
    )


def _json_str(data: Any, key: str) -> str | None:
    value = data.get(key) if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def _json_name(data: Any, default: str) -> str:
    """TS spreads the JSON over the defaults, so a top-level string ``name`` (even ``""``) or number wins."""
    value = data.get("name") if isinstance(data, dict) else None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return js_number_to_string(value)
    return default


def read_json(
    path: str | os.PathLike[str],
    *,
    name: str | None = None,
    network_id: str | None = None,
    identifier: str = "id",
) -> NetworkFile:
    """Read an Infomap ``-o json`` file (v2-io §3).

    Defaults: id = ``network_id`` > the JSON top-level ``id`` (a non-empty string) > the file stem; name = ``name``
    > the JSON ``name`` > the file basename. The JSON ``format``/``haveModules``/``filename``/``size``/
    ``lastModified`` keys, which TS would honour, are ignored (they do not affect the layout).
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    try:
        data = parse_json(text)
    except ValueError as e:
        raise ValueError(
            f"{p.name} is not valid JSON ({e}); expected Infomap JSON output: {_HOW_TO}"
        ) from None
    stat = p.stat()
    return from_json_dict(
        data,
        id=network_id if network_id is not None else (_json_str(data, "id") or p.stem),
        name=name if name is not None else _json_name(data, p.name),
        identifier=identifier,
        filename=p.name,
        size=stat.st_size,
        last_modified=int(stat.st_mtime * 1000),
        where=p.name,
    )
