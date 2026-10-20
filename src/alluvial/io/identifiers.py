"""Ports of ``parsers/set-identifiers.ts``, ``parsers/parse-files.ts`` ``createFile`` and ``parsers/calc-statistics.ts``.

Spec: docs/dev/port-notes/parsers.md §5 and §6.
"""

from __future__ import annotations

import math
import numbers
import warnings
from collections import Counter
from collections.abc import Callable, Sequence
from typing import Any

from .._jscompat import NAN, is_array_index_key, js_num_str, js_number, js_truthy
from .._warnings import user_stacklevel
from ..tree_path import TreePath
from .types import NetworkFile, Node

__all__ = ["calc_statistics", "create_file", "set_identifiers", "warn_duplicate_identifiers"]


def _state_or_node_id(node: Node) -> int | float:
    return node.state_id if node.state_id is not None else node.id


def _identifier_fn(identifier: str) -> Callable[[Node], str | None]:
    if identifier == "id":
        return lambda n: js_num_str(_state_or_node_id(n))
    if identifier == "name":
        return lambda n: n.name if n.name is not None else js_num_str(_state_or_node_id(n))
    return lambda n: None


def set_identifiers(nodes: Sequence[Node], format: str, identifier: str = "id") -> None:
    """Set ``Node.identifier`` (and, for clu, ``path``/``name``) in place, exactly like ``setIdentifiers``.

    Parameters
    ----------
    nodes : sequence of Node
        Parsed nodes; mutated.
    format : str
        ``"tree"``, ``"ftree"``, ``"stree"``, ``"clu"``, ``"json"`` or ``"multilayer-expanded"``. Other formats
        are a no-op, as in TS.
    identifier : {"id", "name"}
        ``"id"`` gives ``state_id ?? id``, ``"name"`` gives ``name ?? state_id ?? id``. Ignored for clu (always
        the state/node id) and multilayer-expanded (always the physical id).
    """
    idfn = _identifier_fn(identifier)
    if format == "multilayer-expanded":
        for n in nodes:
            n.identifier = js_num_str(n.id)
    elif format == "json":
        for n in nodes:
            n.identifier = n.identifier if n.identifier is not None else idfn(n)
            # string paths with ``;`` (stree insignificance) stay strings for TreePath (P3)
            if not isinstance(n.path, list) and not (isinstance(n.path, str) and ";" in n.path):
                n.path = TreePath.to_array(n.path)
    elif format in ("tree", "ftree", "stree"):
        for n in nodes:
            n.identifier = idfn(n)
    elif format == "clu":
        for n in nodes:
            n.path = js_num_str(n.module_id)  # type: ignore[arg-type]
            n.identifier = js_num_str(_state_or_node_id(n))
            n.name = js_num_str(n.id)


def _number_key(value: Any) -> int | float:
    v = js_number(value)
    if math.isnan(v):
        return NAN
    if math.isfinite(v) and v.is_integer():
        return int(v)
    return v


def _js_object_order(d: dict[Any, float]) -> dict[Any, float]:
    """Reorder numeric keys like a JS object: array-index keys ascending, then the rest in insertion order."""
    index_keys = [k for k in d if isinstance(k, int) and is_array_index_key(str(k))]
    other = [k for k in d if not (isinstance(k, int) and is_array_index_key(str(k)))]
    return {k: d[k] for k in sorted(index_keys) + other}


def calc_statistics(nodes: Sequence[Node]) -> dict[str, Any]:
    """Port of ``calcStatistics`` (parsers.md §6), on the raw path strings.

    Returns a dict with ``NetworkFile`` field names: ``flow_distribution``, ``is_multilayer``,
    ``is_state_network``, ``is_expanded``, ``num_layers``, ``num_top_modules``, ``num_levels``.

    Raises
    ------
    ValueError
        For an empty node list (TS throws a ``TypeError``).
    """
    if not nodes:
        raise ValueError("network has no nodes")
    flow_distribution: dict[Any, float] = {}
    layer_ids: set[Any] = set()
    top_modules: set[Any] = set()
    num_levels = 0
    for n in nodes:
        if isinstance(n.path, list):
            parts: list[Any] = n.path
        else:
            parts = n.path.split(":") if n.path is not None else []
            if len(parts) > 1 and parts[-1] == "":
                parts.pop()  # stree trailing ``:`` (E1), as TreePath
        top = _number_key(parts[0] if parts else None)
        top_modules.add(top)
        num_levels = max(num_levels, len(parts))
        acc = flow_distribution.get(top)
        if not js_truthy(acc):
            acc = 0
        flow_distribution[top] = acc + (n.flow if n.flow is not None else 0)
        if n.layer_id is not None:
            layer_ids.add(n.layer_id)
    is_multilayer = nodes[0].layer_id is not None
    return {
        "flow_distribution": _js_object_order(flow_distribution),
        "is_multilayer": is_multilayer,
        "is_state_network": nodes[0].state_id is not None,
        "is_expanded": False if is_multilayer else None,
        "num_layers": len(layer_ids) if layer_ids else None,
        "num_top_modules": len(top_modules),
        "num_levels": num_levels,
    }


def _is_finite_real(value: Any) -> bool:
    """A finite real number, not a bool. Like ``layout`` it accepts NumPy scalars (``numbers.Real``) in a hand-built
    file; JSON and text input only give ``int``/``float``. An ``int`` too large for a float is not finite (it is
    ``Infinity`` in JS)."""
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_network_nodes(nodes: Any, where: str = "") -> None:
    """Port of ``parsers/validate-nodes.ts`` ``validateNetworkNodes`` (fix round E9): every node needs a finite
    numeric ``flow``.

    A NaN, infinite or missing flow makes the numeric sort comparators of the engine inconsistent (the order then
    depends on the sort algorithm) and the geometry NaN, so both engines reject it at load. Raises ``ValueError``
    naming the first bad node (1-based, as in TS).
    """
    pre = f"{where}: " if where else ""
    if not isinstance(nodes, (list, tuple)):
        raise ValueError(f"{pre}the network has no nodes")
    for i, node in enumerate(nodes):
        flow = getattr(node, "flow", None)
        if not _is_finite_real(flow):
            shown = "missing" if flow is None else js_num_str(flow) if isinstance(flow, float) else repr(flow)
            raise ValueError(f"{pre}node {i + 1} has no finite flow ({shown})")


def create_file(
    contents: dict[str, Any],
    *,
    format: str,
    id: str,
    name: str,
    filename: str | None = None,
    size: int = 0,
    last_modified: int = 0,
) -> NetworkFile:
    """Port of ``createFile`` (+ ``calcStatistics``): build a ``NetworkFile`` from parsed contents.

    ``contents`` holds ``nodes`` and header fields under ``NetworkFile`` names; its keys override the defaults,
    as the TS spread does. Statistics overwrite the header's ``num_levels``/``num_top_modules``.
    """
    fields: dict[str, Any] = {
        "filename": name if filename is None else filename,
        "name": name,
        "last_modified": last_modified,
        "size": size,
        "id": id,
        "have_modules": True,
        "format": format,
        **contents,
    }
    nf = NetworkFile(**fields)
    validate_network_nodes(nf.nodes, nf.filename or nf.name or "")
    if nf.have_modules:
        for key, value in calc_statistics(nf.nodes).items():
            setattr(nf, key, value)
    return nf


def warn_duplicate_identifiers(nf: NetworkFile) -> None:
    """Emit a ``UserWarning`` if several nodes of ``nf`` share an identifier (the last one wins in matching)."""
    counts = Counter(n.identifier for n in nf.nodes)
    dups = [k for k, c in counts.items() if c > 1]
    if dups:
        example = ", ".join(repr(k) for k in dups[:3])
        warnings.warn(
            f"network {nf.name!r}: {len(dups)} identifier(s) are shared by several nodes (e.g. {example}); "
            "cross-network matching uses the last node with each identifier",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
