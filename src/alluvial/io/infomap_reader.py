"""``infomap.Infomap`` (or its ``Result``) -> ``NetworkFile``, equal to reading the file Infomap would write.

The target is what the TS app yields for ``result.write_tree/write_flow_tree/write_clu(path, states=s)``
(docs/dev/port-notes/parsers.md §11): rows in ``result.nodes(depth, states=s)`` order, flows and codelength rounded to
6 significant digits (``%g``) unless ``exact=True``. ``infomap`` is never imported at module level.
"""

from __future__ import annotations

import itertools
from typing import Any, Literal

from .identifiers import create_file, set_identifiers
from .types import NetworkFile, Node

__all__ = ["from_infomap", "is_infomap"]


def _g(x: float) -> float:
    return float(f"{x:g}")


MIN_INFOMAP = (2, 14)
"""The first infomap release with the ``Result`` API (``im.run()`` returns it; ``Result.nodes``) this reader uses."""


def _version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in version.split(".")[:3]:
        digits = "".join(itertools.takewhile(str.isdigit, token))
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _too_old_error(module: Any) -> TypeError:
    version = getattr(module, "__version__", "unknown")
    return TypeError(
        f"infomap {version} is too old: reading infomap.Infomap objects needs infomap >= "
        f"{'.'.join(map(str, MIN_INFOMAP))} (the Result API). Upgrade with `pip install -U infomap`, or write the "
        "result with im.write_tree('net.tree') (states=True for state networks) and read that file"
    )


def _result_and_engine(source: Any) -> tuple[Any, Any]:
    result = source if hasattr(source, "_engine") else getattr(source, "_result", None)
    if result is None or not hasattr(result, "nodes"):
        import infomap

        if _version_tuple(getattr(infomap, "__version__", "0")) < MIN_INFOMAP:
            raise _too_old_error(infomap)
        if hasattr(source, "run") and hasattr(source, "_result"):
            raise ValueError("the Infomap object has not been run; call im.run() first")
        if type(source).__name__ == "Network":
            raise TypeError(
                "an infomap.Network keeps no result; pass the Result that net.run() returns, "
                "e.g. alluvial.read(net.run())"
            )
        raise TypeError(
            f"expected an infomap.Infomap that has run, or an infomap Result, got {type(source).__name__}"
        )
    return result, result._engine


def _have_memory(result: Any, engine: Any) -> bool:
    # ``Result.have_memory`` (infomap >= 2.14); ``Infomap.have_memory`` is deprecated.
    value = getattr(result, "have_memory", None)
    if value is None:
        value = engine._core.haveMemory()
    return bool(value)


def _directed(result: Any, engine: Any, version: str) -> bool:
    # What ``write_flow_tree`` writes as ``*Links directed``: the flow model is not undirected. infomap 2.14's
    # ``Result._directed`` is the raw ``--directed`` flag (False for ``flow_model="directed"``), 2.15 fixed it.
    if _version_tuple(version) >= (2, 15):
        return bool(result._directed)
    core = getattr(engine, "_core", None)
    if core is not None and hasattr(core, "isUndirectedFlow"):
        return not bool(core.isUndirectedFlow())
    return bool(result._directed)


def is_infomap(source: Any) -> bool:
    """Whether ``source`` looks like an ``infomap.Infomap``/``Network`` or an infomap ``Result``."""
    module = type(source).__module__ or ""
    return module == "infomap" or module.startswith("infomap.")


def from_infomap(
    source: Any,
    *,
    name: str = "network",
    network_id: str | None = None,
    identifier: str = "id",
    states: bool | None = None,
    format: Literal["tree", "ftree", "clu"] = "tree",
    clu_level: int = 1,
    exact: bool = False,
) -> NetworkFile:
    """Read an ``infomap.Infomap`` that has run (or its ``Result``) into a ``NetworkFile``.

    Parameters
    ----------
    source : infomap.Infomap or infomap.Result
        A run Infomap object (its latest result is used) or a result. Needs infomap >= 2.14.
    name : str, default "network"
        Network name.
    network_id : str, optional
        Network id. Defaults to ``name``.
    identifier : {"id", "name"}, default "id"
        As for the file readers (``set_identifiers``). For state nodes, ``"id"`` is the *state* id and ``"name"`` the
        *physical* node name (the physical id when unnamed); see ``alluvial.io.read``.
    states : bool, optional
        Read state nodes. ``None`` picks them when the result has memory (state or multilayer networks).
        ``False`` mirrors the physical-level ``write_tree(states=False)``.
    format : {"tree", "ftree", "clu"}, default "tree"
        Which written file to mirror. ``"ftree"`` adds ``directed`` (module link records are not reproduced);
        ``"clu"`` uses the module ids at ``clu_level``. ``.tree``/``.clu`` omit hidden bipartite feature nodes.
    clu_level : int, default 1
        ``depth_level`` of ``write_clu``. Only used for ``format="clu"``.
    exact : bool, default False
        Keep full-precision flows and codelength instead of the 6-digit values written to files.

    Returns
    -------
    NetworkFile

    Raises
    ------
    ValueError
        If the Infomap object has not been run.
    TypeError
        For other objects, or an infomap older than 2.14.
    """
    if format not in ("tree", "ftree", "clu"):
        raise ValueError(f"format must be 'tree', 'ftree' or 'clu', got {format!r}")
    result, engine = _result_and_engine(source)
    import infomap

    have_memory = _have_memory(result, engine)
    if states is None:
        states = have_memory
    multilayer = bool(states) and bool(
        getattr(getattr(engine, "network", None), "is_multilayer_network", False)
    )
    num = (lambda x: x) if exact else _g
    bipartite_start_id = int(getattr(engine, "bipartite_start_id", 0) or 0)
    core_im = getattr(getattr(engine, "_core", None), "_im", None)
    hide = (
        format != "ftree" and bipartite_start_id > 0 and bool(getattr(core_im, "hideBipartiteNodes", False))
    )
    depth = clu_level if format == "clu" else 1

    nodes: list[Node] = []
    for n in result.nodes(depth, states=bool(states)):
        if hide and n.node_id >= bipartite_start_id:
            continue
        node = Node(id=n.node_id, flow=num(n.flow), path=None)  # type: ignore[arg-type]
        if format == "clu":
            node.module_id = n.module_id
        else:
            node.path = ":".join(str(p) for p in n.path)
            node.name = str(n.name)
        if states:
            node.state_id = n.state_id
        if multilayer:
            node.layer_id = n.layer_id
        nodes.append(node)
    set_identifiers(nodes, format, identifier)

    contents: dict[str, Any] = {
        "nodes": nodes,
        "version": f"v{infomap.__version__}",
        "codelength": num(result.codelength),
        "relative_codelength_savings": (
            result.relative_codelength_savings
            if exact
            else _g(100 * result.relative_codelength_savings) / 100
        ),
        "higher_order": False,
    }
    if have_memory:
        contents["state_level"] = bool(states)
    if format == "clu" and clu_level >= 0:
        contents["clu_level"] = clu_level
    if bipartite_start_id:
        contents["bipartite_start_id"] = bipartite_start_id
    if format == "ftree":
        contents["directed"] = _directed(result, engine, infomap.__version__)
    return create_file(contents, format=format, id=name if network_id is None else network_id, name=name)
