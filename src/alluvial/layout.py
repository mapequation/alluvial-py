"""Public, pure layout entry point: networks + options -> ``AlluvialGeometry``. Never imports matplotlib.

``LayoutOptions`` carries the layout defaults of the web app and maps to its option names with ``to_ts()``.
"""

# Spec: docs/dev/design.md (Public API) and port-notes/layout.md §3.1. The defaults are those of
# store/DiagramStore.ts:81-96, and to_ts() gives the TS LayoutOpts names.

from __future__ import annotations

import dataclasses
import errno
import math
import numbers
import os
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from ._warnings import user_stacklevel

if TYPE_CHECKING:
    from .geometry import AlluvialGeometry

__all__ = ["LayoutOptions", "NodeInfo", "layout", "save_diagram"]

ModuleSize = Literal["flow", "nodes"]
SortModulesBy = Literal["flow", "nodes", "node_id", "highlight_index"]
VerticalAlign = Literal["bottom", "justify"]

_SORT_TO_TS = {"flow": "flow", "nodes": "nodes", "node_id": "nodeId", "highlight_index": "highlightIndex"}
_SORT_FROM_TS = {v: k for k, v in _SORT_TO_TS.items()}
_MODULE_SIZES = ("flow", "nodes")
_VERTICAL_ALIGNS = ("bottom", "justify")

_TS_NAMES = {
    "height": "height",
    "module_width": "moduleWidth",
    "streamline_fraction": "streamlineFraction",
    "streamline_threshold": "streamlineThreshold",
    "flow_threshold": "flowThreshold",
    "margin_exponent": "marginExponent",
    "zero_margins": "zeroMargins",
    "vertical_align": "verticalAlign",
    "module_size": "moduleSize",
    "sort_modules_by": "sortModulesBy",
}

_NUMERIC = (
    "height",
    "module_width",
    "streamline_fraction",
    "streamline_threshold",
    "flow_threshold",
    "margin_exponent",
)


@dataclass(frozen=True)
class LayoutOptions:
    """Layout options with the web app's defaults. Validated on construction.

    Parameters
    ----------
    height : float, default 600
        Diagram height in layout px. Must be > 0.
    module_width : float, default 80
        Width of each network's module column. Must be > 0.
    streamline_fraction : float, default 2
        Gap between networks as a multiple of ``module_width``. Must be >= 0.
    streamline_threshold : float, default 1
        Streamlines with mean height ``<=`` this (px, not scaled with ``height``) are not drawn. Must be >= 0.
    flow_threshold : float, default 0.005
        Fraction of each network's flow to hide, smallest modules first. Must be in [0, 1).
    margin_exponent : float, default 4
        Module margins are ``2 ** (margin_exponent - 2 * difference_index)``.
    zero_margins : bool, default False
        Put no margin between modules.
    vertical_align : {"bottom", "justify"}, default "bottom"
        ``"justify"`` stretches the margins so every network spans the full height. ``"top"`` is rejected (the
        web app never implemented it).
    module_size : {"flow", "nodes"}, default "flow"
        Module height measure.
    sort_modules_by : {"flow", "nodes", "node_id", "highlight_index"}, default "flow"
        Module order key (descending). ``"node_id"`` is the mean node id.

    Raises
    ------
    TypeError
        If a value has the wrong type.
    ValueError
        If a value is out of range or not one of the allowed choices.

    Examples
    --------
    Pass the fields as keywords to ``layout`` or ``plot``; the geometry keeps the options it ran with:

    >>> import alluvial
    >>> geometry = alluvial.layout([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], height=300, module_width=40)
    >>> geometry.options.height, geometry.options.module_width
    (300.0, 40.0)
    >>> alluvial.LayoutOptions(vertical_align="justify").to_ts()["verticalAlign"]
    'justify'
    """

    height: float = 600.0
    module_width: float = 80.0
    streamline_fraction: float = 2.0
    streamline_threshold: float = 1.0
    flow_threshold: float = 5e-3
    margin_exponent: float = 4.0
    zero_margins: bool = False
    vertical_align: VerticalAlign = "bottom"
    module_size: ModuleSize = "flow"
    sort_modules_by: SortModulesBy = "flow"

    def __post_init__(self) -> None:
        for name in _NUMERIC:
            value = getattr(self, name)
            # numbers.Real also admits numpy scalars (np.int64 is not an int subclass).
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise TypeError(f"{name} must be a number, got {value!r}")
            value = float(value)
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value!r}")
            object.__setattr__(self, name, value)
        if self.height <= 0:
            raise ValueError(f"height must be > 0, got {self.height!r}")
        if self.module_width <= 0:
            raise ValueError(f"module_width must be > 0, got {self.module_width!r}")
        if self.streamline_fraction < 0:
            raise ValueError(f"streamline_fraction must be >= 0, got {self.streamline_fraction!r}")
        if self.streamline_threshold < 0:
            raise ValueError(f"streamline_threshold must be >= 0, got {self.streamline_threshold!r}")
        if not 0 <= self.flow_threshold < 1:
            raise ValueError(f"flow_threshold must be in [0, 1), got {self.flow_threshold!r}")
        if not isinstance(self.zero_margins, bool):
            raise TypeError(f"zero_margins must be a bool, got {self.zero_margins!r}")
        if self.vertical_align not in _VERTICAL_ALIGNS:
            raise ValueError(f"vertical_align must be one of {_VERTICAL_ALIGNS}, got {self.vertical_align!r}")
        if self.module_size not in _MODULE_SIZES:
            raise ValueError(f"module_size must be one of {_MODULE_SIZES}, got {self.module_size!r}")
        if self.sort_modules_by not in _SORT_TO_TS:
            raise ValueError(
                f"sort_modules_by must be one of {tuple(_SORT_TO_TS)}, got {self.sort_modules_by!r}"
            )

    def to_ts(self) -> dict[str, Any]:
        """The options under the web app's option names and values, as a saved diagram stores them."""
        out = {_TS_NAMES[k]: v for k, v in asdict(self).items()}
        out["sortModulesBy"] = _SORT_TO_TS[self.sort_modules_by]
        return out

    @classmethod
    def from_ts(cls, options: Mapping[str, Any]) -> LayoutOptions:
        """Build from the web app's option names (the inverse of ``to_ts()``). Unknown keys raise ``ValueError``."""
        inverse = {v: k for k, v in _TS_NAMES.items()}
        kwargs: dict[str, Any] = {}
        for key, value in options.items():
            if key not in inverse:
                raise ValueError(f"unknown TS layout option {key!r}")
            if key == "sortModulesBy":
                if value not in _SORT_FROM_TS:
                    raise ValueError(f"unknown sortModulesBy {value!r}")
                value = _SORT_FROM_TS[value]
            kwargs[inverse[key]] = value
        return cls(**kwargs)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))


@dataclass(frozen=True)
class NodeInfo:
    """A read-only view of one input node, passed to a ``layout(highlight=callable)``.

    Attributes
    ----------
    network_index : int
        Index of the network (left to right, after splitting layers).
    network_id : str
        Its network id.
    identifier : str
        The string nodes are matched by across networks (see ``layout(identifier=...)``).
    id : int or float
        The (physical) node id.
    state_id, layer_id : int or None
        State and layer ids of state and multilayer networks.
    name : str or None
        The node name.
    flow : float
        The node flow.
    path : str
        The module path, e.g. ``"1:2:3"`` (the last part is the node's rank in its module).
    metadata : Mapping or None
        The node's metadata, read-only.

    Examples
    --------
    >>> import alluvial
    >>> geometry = alluvial.layout(
    ...     [{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}],
    ...     highlight=lambda node: "a" if node.identifier == "a" else None,
    ... )
    >>> [label.label for label in geometry.highlight_labels]
    ['a']
    """

    network_index: int
    network_id: str
    identifier: str
    id: int | float
    state_id: int | float | None
    layer_id: int | float | None
    name: str | None
    flow: float
    path: str
    metadata: Mapping[str, Any] | None


@dataclass(frozen=True)
class ModuleInfo:
    """A read-only view of one module, passed to a ``layout(module_names=callable)``.

    Attributes
    ----------
    network_index : int
        Index of the network (left to right, after splitting layers).
    network_id : str
        Its network id.
    network_name : str
        Its network name.
    id : str
        The module id (path string), e.g. ``"3"`` or ``"1:2"`` after ``module_level``/``expand``.
    path : tuple of int
        The module path components.
    level : int
        The module level (``1`` for top modules).
    flow : float
        The module flow.
    visible : bool
        Whether the module is drawn (its flow is above the flow threshold).
    node_names : tuple of str
        The names of its nodes in descending flow (nodes without a name are left out).

    Examples
    --------
    >>> import alluvial
    >>> geometry = alluvial.layout(
    ...     [{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], module_names=lambda module: f"M{module.id}"
    ... )
    >>> [module.name for module in geometry.networks[0].modules]
    ['M1', 'M2']
    """

    network_index: int
    network_id: str
    network_name: str
    id: str
    path: tuple[int, ...]
    level: int
    flow: float
    visible: bool
    node_names: tuple[str, ...]


class _DefaultColors(str):
    """The default ``colors`` ("module_id"): unlike an explicit value it gives way to ``highlight=`` and to the
    colors of the input."""

    __slots__ = ()


_DEFAULT_COLORS = _DefaultColors("module_id")

ColorOp = Literal["similarity", "module_id", "nodes", "layer", "physical_id", "hierarchy"]
Highlight = Mapping[Any, Iterable[Any]] | Callable[[NodeInfo], Any]
ModuleOrder = Mapping[int | str, Sequence[Any]]
ModuleNames = Mapping[tuple[int | str, str], str] | Callable[["ModuleInfo"], "str | None"]


def layout(
    networks: Iterable[Any],
    *,
    names: Sequence[str] | None = None,
    ids: Sequence[str] | None = None,
    identifier: Literal["id", "name"] = "id",
    split_layers: bool | Sequence[bool] = False,
    colors: ColorOp | None = _DEFAULT_COLORS,
    color_network: int | str | None = None,
    module_level: int | Sequence[int] = 1,
    expand: Iterable[tuple[int | str, str]] | None = None,
    highlight: Highlight | None = None,
    highlight_colors: Sequence[Any] | Mapping[Any, Any] | None = None,
    scheme: str | Sequence[str] | None = None,
    tone: str | None = None,
    offset: float | None = None,
    restore_state: bool = True,
    module_order: ModuleOrder | None = None,
    module_names: ModuleNames | None = None,
    show_bipartite_nodes: bool | None = None,
    **options: Any,
) -> AlluvialGeometry:
    """Lay out an alluvial diagram of one or more partitioned networks.

    Parameters
    ----------
    networks : iterable of str or PathLike, infomap.Infomap, dict or NetworkFile, or a pandas DataFrame
        Networks from left to right. Paths are read by suffix (``.tree``, ``.ftree``, ``.stree``, ``.clu``,
        ``.json``); an ``infomap.Infomap`` must already have run. A ``.zip`` of network files (the web app's zip
        upload, or ``save_diagram``) contributes its files in archive order. A dict is Infomap JSON when its
        ``"nodes"`` is a list of dicts; any other dict is a partition ``{node: module}`` without Infomap
        (``alluvial.partition``): nodes are ids or names matched across networks by key, a module is an int, a
        path string ``"1:2"`` or a tuple of ints, and every node gets flow 1/N. A long-format DataFrame with the
        columns ``network``, ``node``, ``module`` and optionally ``flow`` gives one network per ``network`` value
        (``alluvial.from_dataframe``, which also takes other column names). When no input carries flows (only
        such dicts, or partitions and frames without flows), ``module_size`` and ``sort_modules_by`` default to
        ``"nodes"``.
    names : sequence of str, optional
        Network names, one per network (after splitting layers; numbers are converted with ``str``). Defaults to the file basename, ``"network {i}"``
        for objects (a partition's ``name`` if given), and ``"<name> layer <k>"``-style names for split layers.
    ids : sequence of str, optional
        Network ids, one per network (after splitting layers): unique, without ``"--"``. By default the file stem,
        ``"net{i}"`` for objects or the ``NetworkFile`` id, with colliding ids made unique as ``out``, ``out_2``, ...
        An input that is split gets that suffix before splitting (``out_2_layer1``, ...).
    identifier : {"id", "name"}, default "id"
        How nodes are matched across networks: ``stateId ?? id``, or the node name. Applies to paths, dicts and
        Infomap objects; a ``NetworkFile`` keeps the identifiers it was read with.
    split_layers : bool or sequence of bool, default False
        Split multilayer networks into one network per layer (``alluvial.read(..., split_layers=True)``); a
        sequence gives one flag per input. Split layers match their nodes by physical id.
    colors : {"similarity", "module_id", "nodes", "layer", "physical_id", "hierarchy"} or None, default "module_id"
        Coloring operation applied after the build, as in the web app: by module id (the same id gets the same
        color in every network), matching modules across networks, every node by its module in one network
        (``color_network``), by layer id (multilayer networks), by physical node id (state or multilayer
        networks), or by the module hierarchy (c3's ``hierarchy()``: sub-modules get colors close to their
        parent's, and the same module path gets the same color in every network; use it with
        ``module_level``/``expand``, and ``scheme``, ``tone`` and ``offset`` set the top-module colors). ``None``
        keeps the input colors (gray unless the input carries colors). Not allowed with ``highlight``. The default
        is ``None`` when the input carries colors: Infomap JSON with a top-level ``colors`` (as written by
        ``save_diagram``).
    color_network : int or str, optional
        With ``colors="nodes"``, the network whose modules color the nodes (in every network), as the web app's
        selected network: an index, a network id, or a name given with ``names=`` when exactly one network has it.
        Default the first network. Only allowed with ``colors="nodes"``.
    module_level : int or sequence of int, default 1
        Show sub-modules down to this level (one value, or one per network): every visible module whose sub-modules
        go that deep is expanded, as when clicking modules in the web app. ``1`` shows the top modules. With
        ``colors="similarity"`` a sub-module that is not paired with a module of a neighboring network can stay
        gray, as in the web app.
    expand : iterable of (network, module_id), optional
        Modules to expand first, in order. ``network`` is an index or a network id, ``module_id`` a path string like
        ``"1"`` or ``"1:2"`` (looked up when its turn comes, so ``[(0, "1"), (0, "1:2")]`` works).
    highlight : mapping or callable, optional
        Highlight groups of nodes, each in its own color (the rest stays gray). Either ``{label: identifiers}``
        (matched against node identifiers, ints allowed; an identifier may belong to one label only), or a
        callable ``(NodeInfo) -> label or None`` evaluated once per node. Labels are kept in mapping order (or
        first-appearance order) in ``AlluvialGeometry.highlight_labels``, for ``draw(..., legend=True)``.
    highlight_colors : sequence or mapping, optional
        Colors of the highlight labels (a list aligned with the labels, or ``{label: color}``): color strings
        (any matplotlib color name, ``"#rrggbb"`` or ``"rgb(r, g, b)"``) or RGB tuples in [0, 1]. Defaults to the
        scheme.
    scheme : str or sequence of colors, optional
        The color scheme of the coloring operations: a web-app scheme name (``alluvial.SCHEMES`` lists them, e.g.
        ``"Paired"``, ``"Tableau20"``, ``"C3 Sinebow"``; default ``"C3 Oklch"``, as in the web app) or a list of colors. Also the
        default ``highlight_colors``. The C3 schemes (``"C3 Oklch"``, ``"C3 Turbo"``, ``"C3 Rainbow"``,
        ``"C3 Sinebow"``, ``"C3 Viridis"``) are computed with c3 (https://mapequation.github.io/c3).
    tone : str, optional
        The c3 tone: ``"vivid"``, ``"bright"``, ``"strong"``, ``"deep"``, ``"dark"``, ``"soft"``, ``"pastel"`` or
        ``"muted"``, the lightness and chroma of the C3 schemes and of ``colors="hierarchy"`` with a C3 or an
        interpolated (diverging, sequential or cyclical) scheme. Other schemes ignore it. Default ``"vivid"``, as in
        the web app (or the stored tone of a saved diagram).
    offset : float, optional
        Where c3 puts the first color, in degrees around the hue source: its hue on the OKLCH hue circle
        (``"C3 Oklch"``), else 360 is the whole scheme. Applies where ``tone`` does. Default c3's (245 for
        ``"C3 Oklch"``, else 0), or the stored offset of a saved diagram when its scheme is used.
    restore_state : bool, default True
        Restore what a saved diagram (``save_diagram`` or the web app's "Download diagram") stores besides the
        networks, colors and expanded modules: the options, the color scheme with its tone and offset, the custom
        module orders and the module names, as the web app opens it. Explicit keywords win: a layout option,
        ``scheme``, ``tone`` or ``offset`` given here replaces the stored one (another ``scheme`` drops the stored
        offset), and ``module_order``/``module_names`` replace the stored orders/names. Files from
        different saves, or not all files of one save, restore their module orders and names but not the options
        (warned). ``False`` loads the files as plain Infomap JSON (with their colors and expanded modules).
    module_order : mapping, optional
        ``{network: [module_id, ...]}``: put these visible modules of a network (index, id, or a name given
        with ``names=`` as a string when exactly one network has it) at these positions, listed bottom to top. The unlisted visible modules keep their relative order above them; an ``...``
        (Ellipsis) in the list stands for them, so ``["3", ...]`` puts module 3 at the bottom, ``[..., "3"]`` at
        the top and ``["2", ..., "5"]`` both. Applied after the coloring as one reorder of the web app's
        store (one layout however many modules move; "move up/down" in the web app
        gives the same order), so ``sort_modules_by`` sets the start. Module ids are those shown after
        ``expand``/``module_level`` (e.g. ``"1:2"``); hidden modules cannot be placed.
    module_names : mapping or callable, optional
        Custom module names, shown instead of the node names (as the web app's module name field): either
        ``{(network, module_id): name}`` (network as for ``module_order``) or a callable ``(ModuleInfo) -> str or None``
        called for every module (also hidden ones) after all other steps. Names are kept in
        ``ModuleGeometry.name`` (``save_diagram`` stores them); the labels are drawn on the first and last network
        only, as in the web app.
    show_bipartite_nodes : bool, optional
        ``False`` hides the second node type of bipartite networks (node id >= the network's ``bipartiteStartId``),
        as the web app's "Show bipartite nodes" switch. Default ``True`` (or the stored value of a saved diagram).
    **options
        Fields of ``LayoutOptions``.

    Returns
    -------
    AlluvialGeometry
        Frozen geometry in the web app's SVG coordinates (y down).

    Raises
    ------
    ValueError
        For an Infomap object that has not run, an unreadable or unsupported file, no networks, an invalid option
        value, a module to ``expand`` that does not exist or has no sub-modules, ``colors`` with ``highlight``, an
        unknown ``color_network`` or one without ``colors="nodes"``, or
        a ``module_order``/``module_names`` entry with an unknown network or module, a module given twice, or (for
        ``module_order``) a hidden module.
    FileNotFoundError
        For a path that does not exist.
    TypeError
        For an unknown keyword, a single network not wrapped in a list, or an argument of the wrong type.

    Warns
    -----
    UserWarning
        For state networks matched by state id next to networks matched by node id (``identifier="id"``), a
        ``module_level`` deeper than a network's module tree, ``highlight`` identifiers that match no node,
        duplicate node identifiers within a network, highlight labels drawn gray or in a shared color, and a
        diagram where no node flow is positive.

    Notes
    -----
    The steps run in the web app's store, in this order: build, ``expand``, ``module_level``, the coloring
    (``colors`` or ``highlight``), ``module_order``, then ``module_names``. Each is a sequence of the store's own
    operations, so the geometry matches the web app bit for bit.

    Examples
    --------
    >>> import alluvial
    >>> geometry = alluvial.layout([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], names=["2020", "2021"])
    >>> [network.name for network in geometry.networks]
    ['2020', '2021']
    >>> [len(network.modules) for network in geometry.networks], len(geometry.streamlines)
    ([2, 2], 3)
    """
    from .geometry import build_geometry

    store, highlight_labels = _build_store(
        networks,
        names=names,
        ids=ids,
        identifier=identifier,
        split_layers=split_layers,
        colors=colors,
        color_network=color_network,
        module_level=module_level,
        expand=expand,
        highlight=highlight,
        highlight_colors=highlight_colors,
        scheme=scheme,
        tone=tone,
        offset=offset,
        restore_state=restore_state,
        module_order=module_order,
        module_names=module_names,
        show_bipartite_nodes=show_bipartite_nodes,
        options=options,
    )
    font_size = store.display_options.get("fontSize")
    return build_geometry(
        store.diagram,
        store.options,
        palette=tuple(store.highlight_colors),
        font_size=font_size if _is_positive_number(font_size) else 8.0,
        aggregate_state_names=store.display_options.get("aggregateStateNames") is not False,
        highlight_labels=highlight_labels,
    )


def save_diagram(
    networks: Iterable[Any],
    path: str | os.PathLike[str],
    *,
    loose: bool = False,
    **layout_kwargs: Any,
) -> Path:
    """Lay out ``networks`` like ``layout`` and save the diagram as the web app saves it ("Download diagram").

    The files are "alluvial network files" (formatVersion 1): one Infomap-JSON file per network
    (``00_<name>.json``, ...) with the network name, the palette (``colors``), each node's color index and module
    level, Infomap's own top-level data, and an ``alluvial`` block with the options, the color scheme with its c3
    tone and offset, the module names and any custom module order. The web app opens them (drop the zip, or all files, on "Load networks") with
    the same picture, and ``alluvial.read``/``layout`` load them back exactly. Other Infomap-JSON readers ignore the
    block. The text equals the web app's for the same diagram, apart from ``generator``.

    Parameters
    ----------
    networks, **layout_kwargs
        As for ``layout`` (``names``, ``colors``, ``color_network``, ``module_level``, ``highlight``, ``scheme``, ``tone``, ``offset``,
        ``module_order``,
        ``module_names``, layout options, ...). The writer reads the engine store after these steps, as the web app
        saves its own store.
    path : str or PathLike
        Where to write. By default a zip (``.zip`` is appended if ``path`` has another suffix). With
        ``loose=True``, a directory (created if needed) for the loose files. A ``.json`` path writes the one file of
        a single-network diagram.
    loose : bool, default False
        Write loose files to a directory instead of a zip.

    Returns
    -------
    pathlib.Path
        The path written (the zip, the directory or the ``.json`` file).

    Raises
    ------
    TypeError
        If ``networks`` is an ``AlluvialGeometry`` (pass the networks and ``layout``'s keywords instead).
    ValueError
        For a ``.json`` path and a diagram of more than one network.

    Examples
    --------
    >>> import alluvial, pathlib, tempfile
    >>> networks = [{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}]
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     path = alluvial.save_diagram(networks, pathlib.Path(tmp) / "diagram.zip", names=["2020", "2021"])
    ...     [network.name for network in alluvial.read(path)]
    ['2020', '2021']
    """
    from . import __version__
    from .io.alluvial_format import serialize_diagram

    out = Path(path)
    suffix = out.suffix.lower()
    store, _ = _build_store(networks, **_layout_arguments(layout_kwargs))
    store.highlight_colors = _css_colors(store.highlight_colors)
    files = serialize_diagram(store, generator=f"alluvial (Python) {__version__}")
    if suffix == ".json":
        if len(files) != 1:
            raise ValueError(
                f"save_diagram writes a .json file only for a diagram of one network, got {len(files)} networks; "
                "pass a .zip path (or a directory with loose=True)"
            )
        out.write_text(files[0][1], encoding="utf-8")
    elif loose:
        out.mkdir(parents=True, exist_ok=True)
        for name, text in files:
            (out / name).write_text(text, encoding="utf-8")
    else:
        import zipfile

        if suffix != ".zip":
            out = out.with_name(out.name + ".zip")
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, text in files:
                zf.writestr(name, text.encode("utf-8"))
    return out


def _layout_arguments(kwargs: dict[str, Any]) -> dict[str, Any]:
    """``layout``'s keyword defaults, overridden by ``kwargs``; the rest are layout options."""
    defaults: dict[str, Any] = {
        "names": None,
        "ids": None,
        "identifier": "id",
        "split_layers": False,
        "colors": _DEFAULT_COLORS,
        "color_network": None,
        "module_level": 1,
        "expand": None,
        "highlight": None,
        "highlight_colors": None,
        "scheme": None,
        "tone": None,
        "offset": None,
        "restore_state": True,
        "module_order": None,
        "module_names": None,
        "show_bipartite_nodes": None,
    }
    args = {k: kwargs.pop(k) if k in kwargs else v for k, v in defaults.items()}
    args["options"] = kwargs
    return args


def _css_colors(colors: Sequence[Any]) -> list[Any]:
    """Palette entries as CSS color strings for the web app: hex and ``rgb()`` strings unchanged, other
    matplotlib colors (``"tab:blue"``, ``"C0"``, names) as ``#rrggbb``."""
    from ._palette import parse_color

    out = []
    for color in colors:
        if isinstance(color, str):
            try:
                parse_color(color)
            except ValueError:
                try:
                    import matplotlib.colors as mcolors

                    if color.lower() not in mcolors.CSS4_COLORS:
                        color = mcolors.to_hex(color)
                except (ImportError, ValueError):
                    pass
        out.append(color)
    return out


def _is_positive_number(value: Any) -> bool:
    return (
        isinstance(value, numbers.Real) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    )


def _has_input_colors(f: Any) -> bool:
    return isinstance(f.colors, list) or f.colors is True


def _build_store(
    networks: Iterable[Any],
    *,
    names: Sequence[str] | None,
    ids: Sequence[str] | None,
    identifier: str,
    split_layers: bool | Sequence[bool],
    colors: Any,
    module_level: Any,
    color_network: Any = None,
    expand: Any,
    highlight: Any,
    highlight_colors: Any,
    scheme: str | Sequence[str] | None,
    restore_state: bool,
    tone: str | None = None,
    offset: float | None = None,
    module_order: Any = None,
    module_names: Any = None,
    show_bipartite_nodes: bool | None = None,
    options: dict[str, Any],
) -> tuple[Any, tuple[Any, ...]]:
    """The store steps of ``layout`` (and ``save_diagram``): read, build, expand, module level, coloring, module
    order, module names. Returns the store and the highlight labels."""
    _check_options(options)
    from .geometry import AlluvialGeometry
    from .io import NetworkFile, is_infomap, read

    if isinstance(networks, AlluvialGeometry):
        raise TypeError(
            "networks is an AlluvialGeometry, which is already laid out; draw it with alluvial.draw (to save it "
            "for the web app, pass the networks and the same keywords to alluvial.save_diagram)"
        )

    from .io._partition import from_dataframe, is_dataframe, is_flowless

    if is_dataframe(networks):
        networks = from_dataframe(networks)
    if (
        isinstance(networks, (str, os.PathLike, NetworkFile, Mapping))
        or is_infomap(networks)
        or not isinstance(networks, Iterable)
    ):
        raise TypeError(
            f"networks must be a sequence of networks, got {type(networks).__name__}; wrap a single network in a "
            "list, e.g. layout([path])"
        )
    if not isinstance(restore_state, bool):
        raise TypeError(f"restore_state must be a bool, got {restore_state!r}")
    if show_bipartite_nodes is not None and not isinstance(show_bipartite_nodes, bool):
        raise TypeError(f"show_bipartite_nodes must be a bool, got {show_bipartite_nodes!r}")
    sources = list(networks)
    explicit_colors = type(colors) is not _DefaultColors
    if not isinstance(colors, (str, type(None))) or colors not in _COLOR_OPS:
        raise ValueError(f"colors must be one of {tuple(_COLOR_OPS)}, got {colors!r}")
    if color_network is not None:
        if not (_is_int(color_network) or isinstance(color_network, str)):
            raise TypeError(f"color_network must be a network index, id or name, got {color_network!r}")
        if colors != "nodes":
            raise ValueError(f'color_network requires colors="nodes", got colors={colors!r}')
    if highlight is not None:
        if explicit_colors:
            raise ValueError("colors and highlight are mutually exclusive; pass only one of them")
        if not (callable(highlight) or isinstance(highlight, Mapping)):
            raise TypeError(
                f"highlight must be a mapping {{label: identifiers}} or a callable, got {type(highlight).__name__}"
            )
        colors = None
    elif highlight_colors is not None:
        raise ValueError("highlight_colors requires highlight")
    if scheme is not None and (
        isinstance(scheme, (bytes, Mapping)) or not isinstance(scheme, (str, Sequence))
    ):
        raise TypeError(f"scheme must be a scheme name or a sequence of colors, got {scheme!r}")
    from ._palette import check_offset, check_tone, get_scheme

    if isinstance(scheme, str):
        get_scheme(scheme)  # an unknown name fails before reading
    if tone is not None:
        check_tone(tone)
    offset = check_offset(offset)
    module_level = _check_module_level(module_level)
    expand_items = _check_expand(expand)
    order_items = _check_module_order(module_order)
    name_items = _check_module_names(module_names)
    if not sources:
        raise ValueError("networks is empty; pass at least one network")

    read_items = [_read_network(source, i, identifier) for i, source in enumerate(sources)]
    if any(isinstance(item, list) for item in read_items):  # a zip, a directory or a data frame
        if isinstance(split_layers, Sequence) and not isinstance(split_layers, str):
            raise ValueError(
                "split_layers must be a single bool when a zip, directory or data frame is among the inputs"
            )
        read_items = [nf for item in read_items for nf in (item if isinstance(item, list) else [item])]
    read_files: list[NetworkFile] = read_items
    splits = _check_split(split_layers, len(read_files))

    if all(map(is_flowless, read_files)):
        # no input carries flows (every node has flow 1/N): size and sort modules by node count unless given
        options = {"module_size": "nodes", "sort_modules_by": "nodes", **options}
    opts = LayoutOptions(**options)
    # The web app gives every loaded file a distinct (random) id, and a split layer's original_id is its file's id
    # (colorModuleIdsInAllNetworks tells one split file from several by it): repeated ids of split inputs get the
    # suffix `_<k>` before splitting, as the fixture harness does for every input.
    distinct = _distinct_ids([nf.id for nf in read_files])
    files: list[NetworkFile] = []
    for nf, network_id, split in zip(read_files, distinct, splits, strict=True):
        if split:
            if network_id != nf.id:
                nf = dataclasses.replace(nf, id=network_id)
            files.extend(read(nf, identifier=identifier, split_layers=True))
        else:
            files.append(nf)
    if names is not None:
        if isinstance(names, (str, bytes)) or not isinstance(names, Iterable):
            raise TypeError(f"names must be a sequence of strings, got {names!r}")
        names = [str(name) for name in names]  # e.g. years
        if len(names) != len(files):
            raise ValueError(f"got {len(names)} names for {len(files)} networks")
        files = [dataclasses.replace(f, name=name) for f, name in zip(files, names, strict=True)]
    files = _assign_ids(files, ids)
    # checkColors writes the merged highlight_index onto the nodes of a file with colors (and the merged palette
    # onto a list-palette file): use copies
    files = [
        dataclasses.replace(f, nodes=[dataclasses.replace(n) for n in f.nodes]) if _has_input_colors(f) else f
        for f in files
    ]
    _warn_mixed_identifiers(files)
    _warn_empty(files)
    if module_level != 1:
        _warn_module_level(files, module_level)

    # a saved diagram (alluvial.io.alluvial_format): its options and scheme under the explicit keywords
    from .io.alluvial_format import DISPLAY_OPTION_DEFAULTS, LAYOUT_OPTION_KEYS, read_alluvial_metadata

    saved = read_alluvial_metadata(files) if restore_state else None
    stored = (saved.options if saved is not None else None) or {}
    if any(k in LAYOUT_OPTION_KEYS for k in stored):
        opts = dataclasses.replace(
            LayoutOptions.from_ts({k: v for k, v in stored.items() if k in LAYOUT_OPTION_KEYS}), **options
        )
    explicit_scheme = scheme
    if scheme is None and saved is not None and saved.color_scheme is not None:
        scheme = saved.color_scheme
    if saved is not None and saved.options is not None:
        if tone is None:
            tone = saved.color_tone
        # the stored offset belongs to the stored scheme (offsets differ between hue sources)
        if (
            offset is None
            and saved.has_color_offset
            and (explicit_scheme is None or explicit_scheme == saved.color_scheme)
        ):
            offset = saved.color_offset
    if show_bipartite_nodes is None:
        show_bipartite_nodes = stored.get("showBipartiteNodes", True)
    is_saved = saved is not None and any(block is not None for block in saved.networks)
    if not explicit_colors and highlight is None and (is_saved or any(map(_has_input_colors, files))):
        colors = None  # keep the input colors

    from .engine import DiagramStore
    from .engine.store import HIGHLIGHT_KEY
    from .geometry import HighlightLabel

    store = DiagramStore(
        opts,
        # the store's defaults (the web app's default scheme and tone) apply unless given
        **({} if scheme is None else {"scheme": scheme}),
        **({} if tone is None else {"tone": tone}),
        offset=offset,
        show_bipartite_nodes=show_bipartite_nodes,
        display_options={k: v for k, v in stored.items() if k in DISPLAY_OPTION_DEFAULTS},
    )
    if "defaultHighlightColor" in stored:
        store.default_highlight_color = stored["defaultHighlightColor"]

    labels: list[Any] = []
    if highlight is not None:
        labels, files = _label_nodes(highlight, files)
        label_colors = _label_colors(labels, highlight_colors, store.selected_scheme)

    store.set_networks(files)
    if saved is not None:
        restore_warnings: list[str] = []
        store.restore_saved_order_and_names(
            saved, restore_warnings, order=module_order is None, names=module_names is None
        )
        for message in [*saved.warnings, *restore_warnings]:
            warnings.warn(f"saved diagram: {message}", UserWarning, stacklevel=user_stacklevel())
    if expand_items:
        store.apply_expand_list(expand_items)
    if module_level != 1:
        store.apply_module_level(module_level)

    highlight_labels: tuple[HighlightLabel, ...] = ()
    if highlight is not None:
        _warn_label_colors(store, labels, label_colors)

        def label_of_leaf(leaf: Any) -> int | None:
            md = leaf.metadata
            k = md.get(HIGHLIGHT_KEY) if isinstance(md, Mapping) else None
            return None if k is None else int(k)

        indices = store.apply_highlight(label_of_leaf, label_colors)
        highlight_labels = tuple(
            HighlightLabel(str(label), index, color)
            for label, index, color in zip(labels, indices, label_colors, strict=True)
        )
    else:
        _check_color_op(store, colors)
        op = _COLOR_OPS[colors]
        if colors == "nodes" and color_network is not None:
            network = store.diagram.children[_network_index(store, color_network, "color_network")]
            store.color_nodes_in_modules_in_all_networks(network.network_id)
        elif op is not None:
            getattr(store, op)()
    if order_items:
        store.apply_module_order(
            (_network_index(store, ref, "module_order"), ids) for ref, ids in order_items
        )
    if callable(name_items):
        name_items = _call_module_names(store, name_items)
    if name_items:
        resolved = [(_network_index(store, ref, "module_names"), mid, name) for ref, mid, name in name_items]
        seen: set[tuple[int, str]] = set()
        for network_index, module_id, _ in resolved:
            if (network_index, module_id) in seen:
                network_id = store.diagram.children[network_index].network_id
                raise ValueError(
                    f"module_names: module {module_id!r} of network {network_id!r} is named twice"
                )
            seen.add((network_index, module_id))
        store.apply_module_names(resolved)
    return store, highlight_labels


def _network_index(store: Any, ref: int | str, what: str) -> int:
    """A network index, id or unique name -> its index in the diagram (``ValueError`` naming ``what`` if none)."""
    networks = store.diagram.children
    if _is_int(ref):
        if not 0 <= ref < len(networks):
            hint = ""
            if sum(n.name == str(ref) for n in networks) == 1:
                hint = f"; to refer to the network named {str(ref)!r}, pass the string {str(ref)!r}"
            raise ValueError(f"{what}: no network {ref} (the diagram has {len(networks)} networks{hint})")
        return int(ref)
    for i, network in enumerate(networks):
        if network.network_id == ref:
            return i
    # A network name (``names=``) works too when exactly one network has it and it is not someone's id.
    named = [i for i, network in enumerate(networks) if network.name == ref]
    if len(named) == 1:
        return named[0]
    ids = ", ".join(repr(n.network_id) for n in networks)
    names = ", ".join(repr(n.name) for n in networks)
    detail = f"network ids: {ids}; names: {names}"
    if len(named) > 1:
        detail = f"{len(named)} networks are named {ref!r}, use an index or a network id; {detail}"
    raise ValueError(f"{what}: no network {ref!r} ({detail})")


def _check_module_order(module_order: Any) -> list[tuple[int | str, list[str]]]:
    """``{network: [module_id | ..., ...]}`` -> ``[(network, ids)]`` with ``...`` as ``"..."``."""
    if module_order is None:
        return []
    if not isinstance(module_order, Mapping):
        raise TypeError(
            f"module_order must be a mapping {{network: [module_id, ...]}}, got {type(module_order).__name__}"
        )
    items: list[tuple[int | str, list[str]]] = []
    for ref, ids in module_order.items():
        if not (_is_int(ref) or isinstance(ref, str)):
            raise TypeError(f"module_order keys must be network indices or ids, got {ref!r}")
        if isinstance(ids, (str, bytes)) or not isinstance(ids, Iterable):
            raise TypeError(
                f"module_order[{ref!r}] must be a list of module ids (bottom to top), got {ids!r}"
            )
        listed = list(ids)
        for module_id in listed:
            if module_id is not Ellipsis and not isinstance(module_id, str):
                raise TypeError(
                    f"module_order[{ref!r}]: module ids are strings like '1' or '1:2' (or ...), got {module_id!r}"
                )
        items.append((int(ref) if _is_int(ref) else ref, ["..." if m is Ellipsis else m for m in listed]))
    return items


def _check_module_names(module_names: Any) -> list[tuple[int | str, str, str]] | Callable[..., Any]:
    """``{(network, module_id): name}`` -> ``[(network, module_id, name)]``; a callable is kept."""
    if module_names is None:
        return []
    if callable(module_names) and not isinstance(module_names, Mapping):
        return module_names
    if not isinstance(module_names, Mapping):
        raise TypeError(
            "module_names must be a mapping {(network, module_id): name} or a callable (ModuleInfo) -> name, got "
            f"{type(module_names).__name__}"
        )
    items: list[tuple[int | str, str, str]] = []
    for key, name in module_names.items():
        if (
            not isinstance(key, tuple)
            or len(key) != 2
            or not (_is_int(key[0]) or isinstance(key[0], str))
            or not isinstance(key[1], str)
        ):
            raise TypeError(
                f"module_names keys must be (network index or id, module id string) pairs, got {key!r}"
            )
        if not isinstance(name, str):
            raise TypeError(f"module_names[{key!r}] must be a string, got {name!r}")
        items.append((int(key[0]) if _is_int(key[0]) else key[0], key[1], name))
    return items


def _call_module_names(store: Any, fn: Callable[[ModuleInfo], Any]) -> list[tuple[int, str, str]]:
    """Call ``fn`` for every module (``network.children`` order, networks left to right)."""
    items: list[tuple[int, str, str]] = []
    for i, network in enumerate(store.diagram.children):
        for module in list(network.children):
            leaves = sorted(module.get_leaf_nodes(), key=lambda leaf: -leaf.flow)
            info = ModuleInfo(
                network_index=i,
                network_id=network.network_id,
                network_name=str(network.name),
                id=module.module_id,
                path=tuple(module.path),
                level=module.module_level,
                flow=module.flow,
                visible=module.is_visible,
                node_names=tuple(str(leaf.name) for leaf in leaves if leaf.name is not None),
            )
            name = fn(info)
            if name is None or name == "":
                continue
            if not isinstance(name, str):
                raise TypeError(f"module_names callable must return a string or None, got {name!r}")
            items.append((i, module.module_id, name))
    return items


_COLOR_OPS: dict[str | None, str | None] = {
    "similarity": "color_matching_modules_in_all_networks",
    "module_id": "color_module_ids_in_all_networks",
    "nodes": "color_nodes_in_modules_in_all_networks",
    "layer": "color_by_layer",
    "physical_id": "color_by_physical_id",
    "hierarchy": "color_module_hierarchy_in_all_networks",
    None: None,
}

#: Parameters of ``layout`` besides the ``LayoutOptions`` fields (``plot`` routes keywords with it).
LAYOUT_KEYWORDS = (
    "names",
    "ids",
    "identifier",
    "split_layers",
    "colors",
    "color_network",
    "module_level",
    "expand",
    "highlight",
    "highlight_colors",
    "scheme",
    "tone",
    "offset",
    "restore_state",
    "module_order",
    "module_names",
    "show_bipartite_nodes",
)


def _check_options(options: Mapping[str, Any]) -> None:
    import difflib

    known = LayoutOptions.field_names()
    unknown = [k for k in options if k not in known]
    if not unknown:
        return
    hints = []
    for k in unknown:
        close = difflib.get_close_matches(k, (*known, *LAYOUT_KEYWORDS), n=1)
        hints.append(f"{k!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
    raise TypeError(
        f"layout() got unexpected keyword argument(s) {', '.join(hints)}. It takes {', '.join(LAYOUT_KEYWORDS)} "
        f"and the LayoutOptions fields {', '.join(known)}; drawing options such as ax= go to alluvial.draw or "
        "alluvial.plot"
    )


def _check_color_op(store: Any, colors: str | None) -> None:
    networks = store.diagram.children
    if colors == "layer" and not any(n.is_multilayer for n in networks):
        raise ValueError("colors='layer' needs a multilayer network (nodes with layer ids)")
    if colors == "physical_id" and not any(n.is_higher_order for n in networks):
        raise ValueError(
            "colors='physical_id' needs a state or multilayer network (in a first-order network every node is "
            "its own physical node)"
        )


def _is_int(value: Any) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


def _check_module_level(module_level: Any) -> int | list[int]:
    """``module_level`` as a Python int or list of ints (numpy integers are accepted)."""
    if _is_int(module_level):
        if module_level < 1:
            raise ValueError(f"module_level must be >= 1, got {module_level!r}")
        return int(module_level)
    levels = (
        None
        if isinstance(module_level, (str, bytes, Mapping)) or not isinstance(module_level, Iterable)
        else list(module_level)  # a list, tuple or numpy array
    )
    if levels is None or not all(_is_int(k) and k >= 1 for k in levels):
        raise ValueError(
            f"module_level must be an int >= 1 or one such int per network, got {module_level!r}"
        )
    return [int(k) for k in levels]


def _check_expand(expand: Any) -> list[tuple[int | str, str]]:
    if expand is None:
        return []
    if isinstance(expand, (str, bytes)) or not isinstance(expand, Iterable):
        raise TypeError(f"expand must be a list of (network, module_id) pairs, got {expand!r}")
    items = []
    for item in expand:
        if (
            isinstance(item, (str, bytes))
            or not isinstance(item, Sequence)
            or len(item) != 2
            or not (_is_int(item[0]) or isinstance(item[0], str))
            or not isinstance(item[1], str)
        ):
            raise TypeError(
                f"expand items must be (network index or id, module id string) pairs, got {item!r}"
            )
        items.append((int(item[0]) if _is_int(item[0]) else item[0], item[1]))
    return items


def _check_split(split_layers: Any, n: int) -> list[bool]:
    if isinstance(split_layers, bool):
        return [split_layers] * n
    if isinstance(split_layers, (str, bytes)) or not isinstance(split_layers, Sequence):
        raise TypeError(f"split_layers must be a bool or one bool per network, got {split_layers!r}")
    flags = list(split_layers)
    if len(flags) != n or not all(isinstance(f, bool) for f in flags):
        raise ValueError(f"split_layers must be a bool or one bool per network ({n}), got {split_layers!r}")
    return flags


def _check_strings(what: str, values: Any, n: int) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{what} must be a sequence of strings, got {values!r}")
    values = list(values)
    if len(values) != n:
        raise ValueError(f"got {len(values)} {what} for {n} networks")
    for v in values:
        if not isinstance(v, str):
            raise TypeError(f"{what} must be strings, got {v!r}")
    return values


def _distinct_ids(ids: list[str]) -> list[str]:
    """``ids`` with each repeat renamed ``<id>_<k>`` (smallest ``k >= 2`` not taken); the first one is kept."""
    taken = set(ids)
    seen: set[str] = set()
    out = []
    for network_id in ids:
        new = network_id
        if new in seen:
            k = 2
            while f"{network_id}_{k}" in taken:
                k += 1
            new = f"{network_id}_{k}"
            taken.add(new)
        seen.add(new)
        out.append(new)
    return out


def _is_infomap_json(source: Mapping[Any, Any]) -> bool:
    """A mapping is Infomap JSON when its ``"nodes"`` is a list of dicts; other mappings are ``{node: module}``."""
    nodes = source.get("nodes")
    return isinstance(nodes, list) and all(isinstance(node, Mapping) for node in nodes)


def _read_network(source: Any, i: int, identifier: str) -> Any:
    """One input, read but not split."""
    from .io import NetworkFile, read
    from .io._partition import from_dataframe, is_dataframe, is_partition_network, partition, renamed

    if isinstance(source, NetworkFile):
        if is_partition_network(source):  # alluvial.partition without a name
            return renamed(source, name=f"network {i}", network_id=f"net{i}")
        return source
    if is_dataframe(source):
        return from_dataframe(source)
    if isinstance(source, (str, os.PathLike)):
        if not os.path.exists(source):
            raise FileNotFoundError(errno.ENOENT, "no such network file", os.fspath(source))
        return read(source, identifier=identifier)
    if isinstance(source, Mapping) and not _is_infomap_json(source):
        # a plain {node: module} partition
        return renamed(partition(source), name=f"network {i}", network_id=f"net{i}")
    if isinstance(source, Mapping):
        # a JSON name is used as given, even "" (TS spreads the JSON over the defaults); a number becomes a string
        json_name = source.get("name")
        named = isinstance(json_name, (str, int, float)) and not isinstance(json_name, bool)
        has_id = isinstance(source.get("id"), str) and source["id"] != ""
        return read(
            dict(source),
            name=None if named else f"network {i}",
            network_id=None if has_id or (named and json_name != "") else f"net{i}",
            identifier=identifier,
        )
    return read(source, name=f"network {i}", identifier=identifier, network_id=f"net{i}")


def _assign_ids(files: list[Any], ids: Sequence[str] | None) -> list[Any]:
    """Explicit ``ids``, or the readers' ids with collisions renamed ``out_2``, ``out_3``, ... (first one kept)."""
    if ids is not None:
        new = _check_strings("ids", ids, len(files))
        dup = next((x for x in new if new.count(x) > 1), None)
        if dup is not None:
            raise ValueError(f"duplicate network id {dup!r} in ids")
    else:
        taken = {f.id for f in files}
        used: set[str] = set()
        new = []
        for f in files:
            network_id = f.id
            if network_id in used:
                k = 2
                while f"{network_id}_{k}" in taken or f"{network_id}_{k}" in used:
                    k += 1
                network_id = f"{network_id}_{k}"
            used.add(network_id)
            new.append(network_id)
    for network_id in new:
        if "--" in network_id or network_id == "":
            raise ValueError(
                f"network id {network_id!r} must be non-empty and must not contain '--' (path ids are the file "
                "stem); pass ids=[...] to choose the ids"
            )
    return [
        f if f.id == network_id else dataclasses.replace(f, id=network_id)
        for f, network_id in zip(files, new)
    ]


def _matched_by(f: Any) -> str | None:
    """``"state"`` if the nodes of ``f`` are matched by state id, ``"node"`` if by node id, else None (names)."""
    by_node = True
    for node in f.nodes:
        if node.identifier is None:
            continue
        node_key = _identifier_key(node.id)
        if node.state_id is not None:
            state_key = _identifier_key(node.state_id)
            if node.identifier == state_key != node_key:
                return "state"
        if node.identifier != node_key:
            by_node = False
    return "node" if by_node else None


def _warn_mixed_identifiers(files: list[Any]) -> None:
    """Warn when state networks matched by state id sit next to networks matched by node id."""
    kinds = [_matched_by(f) for f in files]
    if "state" in kinds and "node" in kinds:
        states = [f.name for f, k in zip(files, kinds) if k == "state"]
        nodes = [f.name for f, k in zip(files, kinds) if k == "node"]
        warnings.warn(
            f"the state network(s) {states} match their nodes by state id, but {nodes} by node id, so streamlines "
            "between them join unrelated nodes. Pass identifier='name' to match physical node names, or use the "
            "physical level of the state networks (states=False for infomap.Infomap objects)",
            UserWarning,
            stacklevel=user_stacklevel(),
        )


def _warn_empty(files: list[Any]) -> None:
    """Warn when no node has a positive flow: the web app then draws an empty diagram (the geometry is kept)."""
    if not any(_is_positive_number(n.flow) for f in files for n in f.nodes):
        warnings.warn(
            "every node flow is zero or negative, so the diagram is empty",
            UserWarning,
            stacklevel=user_stacklevel(),
        )


def _warn_module_level(files: list[Any], module_level: int | Sequence[int]) -> None:
    """Warn for networks whose module tree is shallower than the requested ``module_level``."""
    from .tree_path import TreePath

    levels = [module_level] * len(files) if _is_int(module_level) else list(module_level)
    shallow = []
    for f, k in zip(files, levels):  # a length mismatch raises later, in the store
        depth = max((TreePath(node.path).level - 1 for node in f.nodes), default=0)
        if k > max(depth, 1):
            shallow.append((f.name, k, depth))
    if shallow:
        detail = ", ".join(
            f"{name!r} (module_level {k}, deepest level {depth})" for name, k, depth in shallow
        )
        hint = (
            "; a two-level partition (Infomap two_level=True or a .clu file) has no sub-modules"
            if any(depth <= 1 for _, _, depth in shallow)
            else ""
        )
        warnings.warn(
            f"module_level is deeper than the module tree of {detail}; their deepest modules are shown{hint}",
            UserWarning,
            stacklevel=user_stacklevel(),
        )


# ------------------------------------------------------------------------------------------------------- highlight


def _identifier_key(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        from ._jscompat import js_num_str

        return js_num_str(float(value) if not isinstance(value, int) else value)
    raise TypeError(f"highlight identifiers must be strings or numbers, got {value!r}")


def _is_number_key(key: str) -> bool:
    try:
        float(key)
    except ValueError:
        return False
    return True


def _identifier_hint(missing: list[str], files: list[Any]) -> str:
    """A hint at ``identifier=`` when the unmatched keys look like names but nodes are matched by id, or v.v."""
    kinds = {_matched_by(f) for f in files}
    if any(not _is_number_key(key) for key in missing) and kinds <= {"node", "state"}:
        return "; nodes are matched by id, pass identifier='name' to match node names"
    if all(_is_number_key(key) for key in missing) and None in kinds:
        return "; nodes are matched by name, pass identifier='id' to match node ids"
    return ""


def _node_info(i: int, f: Any, node: Any) -> NodeInfo:
    from types import MappingProxyType

    from .tree_path import TreePath

    md = node.metadata
    return NodeInfo(
        network_index=i,
        network_id=f.id,
        identifier=node.identifier,
        id=node.id,
        state_id=node.state_id,
        layer_id=node.layer_id,
        name=node.name,
        flow=node.flow,
        path=str(TreePath(node.path)),
        metadata=MappingProxyType(dict(md)) if isinstance(md, Mapping) else None,
    )


def _label_nodes(highlight: Any, files: list[Any]) -> tuple[list[Any], list[Any]]:
    """The highlight labels in index order, and copies of ``files`` whose labeled nodes carry their label index in
    the private metadata key (read back from the leaves by ``apply_highlight``)."""
    from .engine.store import HIGHLIGHT_KEY

    per_file: list[list[int | None]] = []
    if isinstance(highlight, Mapping):
        labels = list(highlight)
        label_of: dict[str, int] = {}
        for k, label in enumerate(labels):
            members = highlight[label]
            if isinstance(members, (str, bytes)) or not isinstance(members, Iterable):
                raise TypeError(
                    f"highlight[{label!r}] must be an iterable of node identifiers, got {type(members).__name__}"
                )
            for value in members:
                key = _identifier_key(value)
                if label_of.setdefault(key, k) != k:
                    raise ValueError(
                        f"node {key!r} is listed under two highlight labels, {labels[label_of[key]]!r} and {label!r}"
                    )
        found: set[str] = set()
        for f in files:
            row = []
            for node in f.nodes:
                k = label_of.get(node.identifier)
                if k is not None:
                    found.add(node.identifier)
                row.append(k)
            per_file.append(row)
        missing = [key for key in label_of if key not in found]
        if missing:
            warnings.warn(
                f"highlight: {len(missing)} of {len(label_of)} identifiers match no node in any network (e.g. "
                f"{', '.join(map(repr, missing[:3]))}){_identifier_hint(missing, files)}",
                UserWarning,
                stacklevel=user_stacklevel(),
            )
    else:
        labels = []
        index: dict[Any, int] = {}
        for i, f in enumerate(files):
            row = []
            for node in f.nodes:
                label = highlight(_node_info(i, f, node))
                if label is None:
                    row.append(None)
                    continue
                if label not in index:
                    index[label] = len(labels)
                    labels.append(label)
                row.append(index[label])
            per_file.append(row)
        if not labels:
            warnings.warn(
                "highlight: the function returned None for every node, so nothing is highlighted",
                UserWarning,
                stacklevel=user_stacklevel(),
            )
    if len({str(label) for label in labels}) != len(labels):
        raise ValueError(f"highlight labels must be distinct as strings, got {labels!r}")

    out = []
    for f, row in zip(files, per_file, strict=True):
        if not any(k is not None for k in row):
            out.append(f)
            continue
        nodes = []
        for node, k in zip(f.nodes, row, strict=True):
            if k is not None:
                md = dict(node.metadata) if isinstance(node.metadata, Mapping) else {}
                md[HIGHLIGHT_KEY] = str(k)
                node = dataclasses.replace(node, metadata=md)
            nodes.append(node)
        out.append(dataclasses.replace(f, nodes=nodes))
    return labels, out


def _color_string(color: Any) -> str:
    if isinstance(color, str):
        return color
    if (
        isinstance(color, Sequence)
        and len(color) in (3, 4)
        and all(isinstance(c, numbers.Real) and not isinstance(c, bool) and 0 <= c <= 1 for c in color)
    ):
        return "#" + "".join(f"{round(float(c) * 255):02x}" for c in color[:3])
    raise TypeError(f"highlight colors must be color strings or RGB tuples in [0, 1], got {color!r}")


def _label_colors(labels: list[Any], highlight_colors: Any, scheme: Sequence[str]) -> list[str]:
    if highlight_colors is None:
        return [scheme[k % len(scheme)] for k in range(len(labels))]
    if isinstance(highlight_colors, Mapping):
        missing = [label for label in labels if label not in highlight_colors]
        if missing:
            raise ValueError(f"highlight_colors has no color for label(s) {missing!r}")
        return [_color_string(highlight_colors[label]) for label in labels]
    if isinstance(highlight_colors, str) or not isinstance(highlight_colors, Sequence):
        raise TypeError(
            f"highlight_colors must be a sequence or a mapping of colors, got {highlight_colors!r}"
        )
    if len(highlight_colors) < len(labels):
        raise ValueError(f"got {len(highlight_colors)} highlight_colors for {len(labels)} labels")
    return [_color_string(c) for c in list(highlight_colors)[: len(labels)]]


def _warn_label_colors(store: Any, labels: list[Any], colors: list[str]) -> None:
    gray = [str(label) for label, c in zip(labels, colors, strict=True) if c == store.default_highlight_color]
    if gray:
        warnings.warn(
            f"highlight: label(s) {gray} use the default color {store.default_highlight_color} and are drawn gray",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
    seen: dict[str, Any] = {}
    shared = []
    for label, c in zip(labels, colors, strict=True):
        if c in seen and c != store.default_highlight_color:
            shared.append((seen[c], label))
        seen.setdefault(c, label)
    if shared:
        warnings.warn(
            f"highlight: labels share a color and cannot be told apart: {shared}",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
