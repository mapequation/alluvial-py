"""Input records: ``NetworkFile``, its ``Node`` rows and the ftree module record.

``None`` stands for a missing value. Paths are kept raw (``str`` from text files, ``list`` from JSON input).
"""

# Mirrors parsers/types.ts (Node, NetworkFile). Spec: docs/dev/port-notes/parsers.md §1. Field names are the
# snake_case TS names; None stands for both JS undefined and null; only TreePath interprets the paths.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = ["Format", "InfomapModule", "Link", "NetworkFile", "Node"]

Format = Literal["json", "clu", "tree", "ftree", "stree", "multilayer-expanded", "net"]


@dataclass
class Node:
    """One node row of a network file (TS ``Node``).

    Attributes
    ----------
    id : int or float
        ``node_id`` column (physical id). Integral ids are ``int``.
    flow : float
        Node flow.
    path : str or list
        Raw module path, e.g. ``"1:2:3"``, ``"1:2;3;"`` or (clu, after ``set_identifiers``) ``"5"``.
    state_id, layer_id : int, optional
        ``state_id`` / ``layer_id`` columns.
    name : str, optional
        Node name (for clu set to the id string by ``set_identifiers``).
    identifier : str, optional
        Cross-network identity set by ``set_identifiers``.
    module_id : int, optional
        clu ``module`` column.
    highlight_index, module_level : int, optional
        Only from JSON input.
    metadata : dict, optional
        Only from JSON input.
    color : str, optional
        Only from JSON input: the node ``color`` that ``checkColors`` turns into ``highlight_index`` when the
        file has ``colors: true``.
    """

    id: int | float
    flow: float
    path: str | list
    state_id: int | float | None = None
    layer_id: int | float | None = None
    name: str | None = None
    identifier: str | None = None
    module_id: int | float | None = None
    highlight_index: int | None = None
    module_level: int | None = None
    metadata: dict[str, Any] | None = None
    color: Any = None


@dataclass
class Link:
    """A module-level link of an ftree ``*Links`` section."""

    source: int | float
    target: int | float
    flow: float


@dataclass
class InfomapModule:
    """An ftree ``*Links <path> …`` module record (TS ``Module`` from ``@mapequation/infomap``).

    ``path`` is ``[0]`` for the root. Missing columns are ``None``.
    """

    path: list[int]
    enter_flow: float | None = None
    exit_flow: float | None = None
    num_edges: int | None = None
    num_children: int | None = None
    links: list[Link] = field(default_factory=list)


@dataclass
class NetworkFile:
    """A parsed network file, as ``alluvial.read`` and ``alluvial.partition`` return it.

    Besides the attributes below, it holds the file's Infomap header (``codelength``, ``directed``, ...) and
    statistics (``is_state_network``, ``is_multilayer``, ``num_top_modules``, ...).

    Attributes
    ----------
    id : str
        Network id. Must be unique within a diagram and must not contain ``"--"``; readers default it to the
        file stem.
    name : str
        Display name; readers default it to the file basename.
    format : str
        ``"tree"``, ``"ftree"``, ``"stree"``, ``"clu"``, ...
    nodes : list of Node
        Node rows in file order (the order decides module creation order and every downstream tie-break).

    Examples
    --------
    >>> import dataclasses, alluvial
    >>> nf = alluvial.partition({"a": 1, "b": 1, "c": 2}, name="2020")
    >>> nf.id, nf.name, nf.num_top_modules
    ('2020', '2020', 2)
    >>> renamed = dataclasses.replace(nf, id="first", name="First year")
    >>> [network.name for network in alluvial.layout([renamed, alluvial.partition({"a": 1, "b": 2, "c": 2})]).networks]
    ['First year', 'network 1']
    """

    id: str
    name: str
    format: str
    nodes: list[Node]
    filename: str = ""
    size: int = 0
    last_modified: int = 0
    have_modules: bool = True
    # header (parsers.md §2.4)
    version: str | None = None
    args: str | None = None
    started_at: str | None = None
    completed_in: float | None = None
    codelength: float | None = None
    relative_codelength_savings: float | None = None
    flow_model: str | None = None
    higher_order: bool | None = None
    state_level: bool | None = None
    clu_level: int | None = None
    bipartite_start_id: int | None = None
    # ftree link section
    directed: bool | None = None
    modules: list[InfomapModule] | None = None
    # calcStatistics (parsers.md §6)
    flow_distribution: dict[Any, float] | None = None
    is_state_network: bool | None = None
    is_multilayer: bool | None = None
    is_expanded: bool | None = None
    num_top_modules: int | None = None
    num_levels: int | None = None
    num_layers: int | None = None
    # infomap / .net workflow and multilayer (not read by the engine in v1)
    network: str | None = None
    num_trials: int | None = None
    two_level: bool | None = None
    layer_id: int | None = None
    original_id: str | None = None
    layers: list[dict[str, Any]] | None = None
    # JSON top-level ``colors`` (TS ``checkColors``: a list of colors, or ``true`` for per-node ``color``)
    colors: Any = None
    # JSON top-level ``modules`` as read (``modules`` holds the parsed records), written back by ``save_diagram``
    raw_modules: list[Any] | None = None
    # JSON top-level ``alluvial``: a saved diagram's metadata block, as read (``alluvial.io.alluvial_format``)
    alluvial: Any = None
