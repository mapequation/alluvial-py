"""Partitions without Infomap: ``{node: module}`` mappings and long-format data frames -> ``NetworkFile``.

pandas is not a dependency: data frames are recognized by duck typing (``columns`` and ``itertuples``/``to_dict``)
and pandas is never imported here.
"""

from __future__ import annotations

import dataclasses
import math
import numbers
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .identifiers import create_file
from .types import NetworkFile, Node

__all__ = ["from_dataframe", "is_dataframe", "is_flowless", "is_partition_network", "partition", "renamed"]

_PATH = re.compile(r"\d+(?::\d+)*")
_INFO = "_alluvial_partition"


@dataclass(frozen=True)
class _PartitionInfo:
    """What ``partition`` records on its ``NetworkFile`` for ``layout``: whether flows were given (else every node
    has flow 1/N) and whether a name was given (else ``layout`` names it ``"network {i}"``)."""

    has_flows: bool
    named: bool


def _info(nf: Any) -> _PartitionInfo | None:
    info = getattr(nf, _INFO, None)
    return info if isinstance(info, _PartitionInfo) else None


def is_flowless(nf: Any) -> bool:
    """True for a ``NetworkFile`` made by ``partition`` without flows (every node has flow 1/N)."""
    info = _info(nf)
    return info is not None and not info.has_flows


def is_partition_network(nf: Any) -> bool:
    """True for a ``NetworkFile`` made by ``partition`` without a name."""
    info = _info(nf)
    return info is not None and not info.named


def renamed(nf: NetworkFile, *, name: str, network_id: str) -> NetworkFile:
    """``nf`` with another name and id, keeping what ``partition`` recorded on it."""
    new = dataclasses.replace(nf, name=name, id=network_id)
    info = _info(nf)
    if info is not None:
        setattr(new, _INFO, info)
    return new


def is_dataframe(obj: Any) -> bool:
    """Duck-typed data frame check (pandas and look-alikes); never imports pandas."""
    return (
        not isinstance(obj, (Mapping, str, bytes))
        and hasattr(obj, "columns")
        and (hasattr(obj, "itertuples") or hasattr(obj, "to_dict"))
    )


def _is_int(value: Any) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _module_path(node: Any, module: Any) -> str:
    """A module value (int, ``"1:2"`` or a sequence of ints) as a tree path string ``"1:2"``."""
    parts: list[Any] | None = None
    if _is_int(module):
        parts = [module]
    elif isinstance(module, str) and _PATH.fullmatch(module):
        parts = [int(part) for part in module.split(":")]
    elif isinstance(module, (tuple, list)) and module and all(map(_is_int, module)):
        parts = list(module)
    if parts is None or any(p < 1 for p in parts):
        raise ValueError(
            f"node {node!r} has module {module!r}; a module is a positive int (top module), a tree path string "
            'like "1:2", or a tuple of positive ints like (1, 2). Module ids start at 1, as in Infomap'
        )
    return ":".join(str(int(p)) for p in parts)


def _check_flow(node: Any, flow: Any) -> float:
    ok = isinstance(flow, numbers.Real) and not isinstance(flow, bool)
    if ok:
        try:
            ok = math.isfinite(flow) and flow >= 0
        except OverflowError:
            ok = False
    if not ok:
        raise ValueError(f"node {node!r} has flow {flow!r}; flows must be non-negative finite numbers")
    return float(flow)


def partition(
    modules: Mapping[Any, Any], flows: Mapping[Any, Any] | None = None, *, name: str | None = None
) -> NetworkFile:
    """One network from a mapping of node ids or names to modules, without Infomap.

    Parameters
    ----------
    modules : mapping
        ``{node: module}``. A node is an id (int) or a name (str); nodes are matched across networks by this key
        (whatever ``layout(identifier=...)`` says). A module is a positive int (a top module), a tree path
        string ``"1:2"`` (sub-module 2 of module 1) or a tuple or list of positive ints ``(1, 2)``; module ids start
        at 1, as in Infomap. The mapping order is the node order.
    flows : mapping, optional
        ``{node: flow}`` with one non-negative finite number per node of ``modules``. The flows are normalized to
        sum to 1, as Infomap's flows do. Without ``flows`` every node gets flow 1/N, N being the number of nodes.
    name : str, optional
        Network name (and id, unless it is empty or contains ``"--"``). ``layout`` names an unnamed partition
        ``"network {i}"``, as other objects.

    Returns
    -------
    NetworkFile
        Nodes in mapping order. An int node keeps its value as node id; a named node gets its 1-based position as
        node id and the key as name. A node's path is its module's path plus its position in that module, as in
        Infomap's ``.tree`` files: ``"2:1:3"`` is the third node of sub-module ``"2:1"``.

    Raises
    ------
    ValueError
        For no nodes, a module value of another kind (or below 1), a key that is neither str nor int, two keys
        with the same string (``1`` and ``"1"``), or flows that are negative, not finite, missing for a node, given
        for a node not in ``modules``, or all zero.
    TypeError
        If ``modules`` or ``flows`` is not a mapping, or ``name`` is not a string.

    Notes
    -----
    A diagram of only flow-less networks (``partition`` without ``flows``, plain ``{node: module}`` dicts in
    ``layout``) sizes and sorts its modules by node count: ``module_size`` and ``sort_modules_by`` default to
    ``"nodes"`` there, unless given.

    Examples
    --------
    >>> import alluvial
    >>> nf = alluvial.partition({"Ann": 1, "Bo": 1, "Cy": "2:1"}, name="2020")
    >>> [(n.name, n.path) for n in nf.nodes]
    [('Ann', '1:1'), ('Bo', '1:2'), ('Cy', '2:1:1')]
    >>> [n.flow for n in alluvial.partition({1: 1, 2: (1, 2)}).nodes]
    [0.5, 0.5]
    >>> [n.flow for n in alluvial.partition({"Ann": 1, "Bo": 2}, flows={"Ann": 3, "Bo": 1}).nodes]
    [0.75, 0.25]

    Plain dicts work directly as networks in ``layout`` and ``plot``:

    >>> geom = alluvial.layout([{"Ann": 1, "Bo": 1, "Cy": 2}, {"Ann": 1, "Bo": 2, "Cy": "2:1"}], names=["2020", "2021"])
    >>> [network.name for network in geom.networks]
    ['2020', '2021']
    """
    if not isinstance(modules, Mapping):
        raise TypeError(f"modules must be a mapping {{node: module}}, got {type(modules).__name__}")
    if flows is not None and not isinstance(flows, Mapping):
        raise TypeError(f"flows must be a mapping {{node: flow}}, got {type(flows).__name__}")
    if name is not None and not isinstance(name, str):
        raise TypeError(f"name must be a string, got {name!r}")
    if not modules:
        raise ValueError("modules is empty; a network needs at least one node")
    nodes: list[Node] = []
    seen: dict[str, Any] = {}
    # A node's tree path is its module's path plus its 1-based position in that module, as in Infomap's .tree files
    # ("1:2:3" is node 3 of sub-module 2 of module 1), so a module path like "1:2" makes a sub-module.
    in_module: dict[str, int] = {}
    for position, (key, module) in enumerate(modules.items(), start=1):
        module_path = _module_path(key, module)
        in_module[module_path] = in_module.get(module_path, 0) + 1
        path = f"{module_path}:{in_module[module_path]}"
        if _is_int(key):
            node = Node(id=int(key), flow=0.0, path=path, name=str(int(key)))
        elif isinstance(key, str):
            node = Node(id=position, flow=0.0, path=path, name=key)
        else:
            raise ValueError(f"node {key!r} must be a str (name) or an int (id), got {type(key).__name__}")
        node.identifier = node.name
        if node.identifier in seen:
            raise ValueError(f"nodes {seen[node.identifier]!r} and {key!r} have the same identifier")
        seen[node.identifier] = key  # type: ignore[index]
        nodes.append(node)
    if flows is None:
        for node in nodes:
            node.flow = 1 / len(nodes)
    else:
        extra = [k for k in flows if k not in modules]
        if extra:
            raise ValueError(f"flows has node(s) not in modules: {', '.join(repr(k) for k in extra[:3])}")
        values = []
        for key in modules:
            if key not in flows:
                raise ValueError(f"flows has no flow for node {key!r}")
            values.append(_check_flow(key, flows[key]))
        total = math.fsum(values)
        if total == 0:
            raise ValueError("flows sum to 0; at least one node needs a positive flow")
        for node, value in zip(nodes, values, strict=True):
            node.flow = value / total
    named = name is not None
    network_id = name if name and "--" not in name else "network"
    nf = create_file({"nodes": nodes}, format="tree", id=network_id, name=name if named else "network")
    setattr(nf, _INFO, _PartitionInfo(has_flows=flows is not None, named=named))
    return nf


def _column(df: Any, column: str) -> list[Any]:
    values = df[column]
    return values.tolist() if hasattr(values, "tolist") else list(values)


def _network_order(df: Any, column: str, values: list[Any]) -> list[Any]:
    """Category order for a pandas Categorical column (unused categories dropped), else first appearance."""
    series = df[column]
    if getattr(getattr(series, "dtype", None), "name", None) == "category":
        present = set(values)
        return [c for c in series.cat.categories.tolist() if c in present]
    return list(dict.fromkeys(values))


def from_dataframe(
    df: Any,
    *,
    network: str = "network",
    node: str = "node",
    module: str = "module",
    flow: str | None = None,
) -> list[NetworkFile]:
    """Networks from a long-format data frame with one row per (network, node), without Infomap.

    Parameters
    ----------
    df : pandas.DataFrame
        The rows. pandas is not required by alluvial; any data frame with ``columns`` and column access works.
    network, node, module : str, default "network", "node", "module"
        Column names: the network of a row, its node (id or name, matched across networks) and its module (as in
        ``partition``: an int, a path string ``"1:2"`` or a tuple of ints).
    flow : str, optional
        The flow column. If ``None`` (the default), a column named ``"flow"`` is used when there is one;
        otherwise every node gets flow 1/N. Flows are normalized to sum to 1 per network.

    Returns
    -------
    list of NetworkFile
        One ``partition`` per network, in order of first appearance, or in category order for a pandas
        Categorical network column. A network's name is ``str(value)``.

    Raises
    ------
    ValueError
        For a missing column, a node twice in one network, an empty frame, or any value ``partition`` rejects.
    TypeError
        If ``df`` is not a data frame.

    Examples
    --------
    >>> import alluvial, pandas as pd
    >>> df = pd.DataFrame({"year": [2020, 2020, 2021, 2021], "who": ["Ann", "Bo", "Ann", "Bo"],
    ...                    "community": [1, 2, 1, 1]})
    >>> networks = alluvial.from_dataframe(df, network="year", node="who", module="community")
    >>> [(nf.name, [n.path for n in nf.nodes]) for nf in networks]
    [('2020', ['1:1', '2:1']), ('2021', ['1:1', '1:2'])]

    With the default column names, pass the frame straight to ``layout`` or ``plot``:

    >>> df = df.rename(columns={"year": "network", "who": "node", "community": "module"})
    >>> [network.name for network in alluvial.layout(df).networks]
    ['2020', '2021']
    """
    if not is_dataframe(df):
        raise TypeError(f"df must be a data frame, got {type(df).__name__}")
    for what, column in (("network", network), ("node", node), ("module", module), ("flow", flow)):
        if column is not None and not isinstance(column, str):
            raise TypeError(f"{what} must be a column name (str), got {column!r}")
    columns = [str(c) for c in df.columns]
    if flow is None and "flow" in columns:
        flow = "flow"
    missing = [c for c in (network, node, module, flow) if c is not None and c not in columns]
    if missing:
        raise ValueError(
            f"the data frame has no column(s) {', '.join(repr(c) for c in missing)}; its columns are "
            f"{columns}. Pass network=, node=, module= (and flow=) to name the columns"
        )
    network_values = _column(df, network)
    if not network_values:
        raise ValueError("the data frame has no rows")
    node_values = _column(df, node)
    module_values = _column(df, module)
    flow_values = _column(df, flow) if flow is not None else None
    rows: dict[Any, tuple[dict[Any, Any], dict[Any, Any]]] = {}
    for i, (net, key, mod) in enumerate(zip(network_values, node_values, module_values, strict=True)):
        mods, flws = rows.setdefault(net, ({}, {}))
        if key in mods:
            raise ValueError(f"node {key!r} appears more than once in network {net!r}")
        mods[key] = mod
        if flow_values is not None:
            flws[key] = flow_values[i]
    return [
        partition(rows[net][0], rows[net][1] if flow is not None else None, name=str(net))
        for net in _network_order(df, network, network_values)
    ]
