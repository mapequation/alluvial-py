"""Frozen geometry: the only contract between the layout engine and the renderers.

Coordinates are the web app's SVG ones: x right, y down, layout px; the diagram spans ``[0, width] x [0, height]``.
Never imports matplotlib.
"""

# Spec: docs/dev/design.md (Geometry contract) and port-notes/streamlines.md §7.

from __future__ import annotations

import dataclasses
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from ._jscompat import js_number_to_string

if TYPE_CHECKING:
    from .layout import LayoutOptions

__all__ = [
    "CLOSEPOLY",
    "CURVE4",
    "LINETO",
    "MOVETO",
    "AlluvialGeometry",
    "GroupGeometry",
    "HighlightLabel",
    "Label",
    "ModuleGeometry",
    "NetworkGeometry",
    "OutlineGeometry",
    "StreamlineGeometry",
    "build_geometry",
]

# matplotlib.path.Path codes, without importing matplotlib.
MOVETO = 1
LINETO = 2
CURVE4 = 4
CLOSEPOLY = 79

SNAP_THRESHOLD = 1e-6

#: Number of label names offered to renderers in ``ModuleGeometry.name_candidates``.
NAME_CANDIDATES = 25

Anchor = Literal["start", "end", "middle"]


class _ToDict:
    def to_dict(self) -> dict[str, Any]:
        """A JSON-compatible dict (tuples become lists, nested dataclasses become dicts)."""
        return _to_jsonable(self)


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class Label(_ToDict):
    """A text label at ``(x, y)``.

    Attributes
    ----------
    text : str
        Text; multi-line module labels join the names with ``"\\n"`` in top-to-bottom order.
    x, y : float
        Anchor point. For module labels ``y`` is the module's vertical center and line ``center_line`` is
        vertically centered on it (SVG ``dominant-baseline: middle``). For network names ``y`` is
        ``network.height + 20`` and the web app puts the first baseline one network font size below it.
    anchor : {"start", "end", "middle"}
        SVG ``text-anchor``.
    center_line : int
        Index of the line centered on ``y`` (``ceil(n / 2) - 1`` for an n-line module label, else 0).
    """

    text: str
    x: float
    y: float
    anchor: Anchor
    center_line: int = 0


@dataclass(frozen=True)
class GroupGeometry(_ToDict):
    """A highlight group: a colored slice of a module. ``highlight_index`` -1 is the default color."""

    highlight_index: int
    insignificant: bool
    x: float
    y: float
    width: float
    height: float
    flow: float


@dataclass(frozen=True)
class ModuleGeometry(_ToDict):
    """A visible module of a network.

    Attributes
    ----------
    id : str
        Module path string, e.g. ``"3"``.
    path : tuple of int
        Module path components.
    network_index : int
        Index of the network (left to right).
    highlight_index : int
        The highlight index of the module's largest group.
    groups : tuple of GroupGeometry
        In the web app's group order: significant first, then by highlight index.
    label : Label or None
        Name label; only modules of the first (anchor ``"end"``) and last (anchor ``"start"``) network have one.
    largest_leaf_names : tuple of str
        Label names in descending flow (aggregated to physical names for state networks), capped by the web
        app's lines-per-module rule at layout px (``label.text`` joins them).
    name_candidates : tuple of str
        For labeled modules only: ``largest_leaf_names`` followed by the next largest names, up to
        ``NAME_CANDIDATES`` in total. Renderers that size labels at their own scale (``alluvial.mpl``) pick
        lines from these, so a tall axes or a small font can show more names than a 600 px web view.
    level : int
        The module level (``1`` for top modules; deeper after ``module_level``/``expand``).
    max_level : int
        The deepest level the module could be expanded to; ``> level`` means it has
        sub-modules.
    order : int or None
        Index of the module in the network's hierarchical draw order (breadth first,
        interleaved with ``NetworkGeometry.outlines``). In a flat diagram it is the index in ``modules``.
    name_highlight_indices : tuple of int
        Highlight index of each label name, aligned with ``name_candidates`` (or ``largest_leaf_names`` when there
        are no candidates). The web app colors each label line with it (black for -1).
    name_insignificant : tuple of bool
        Whether each label name is an insignificant node (drawn brighter); always False for aggregated names.
    name : str
        The module's custom name (restored from a saved web-app diagram), or ``""``. The web
        app shows it, when set, as the module's label instead of the largest leaf names (``label`` keeps the leaf
        names).
    """

    id: str
    path: tuple[int, ...]
    network_index: int
    flow: float
    x: float
    y: float
    width: float
    height: float
    highlight_index: int
    groups: tuple[GroupGeometry, ...]
    label: Label | None
    largest_leaf_names: tuple[str, ...]
    name_candidates: tuple[str, ...] = ()
    level: int = 1
    max_level: int = 1
    order: int | None = None
    name_highlight_indices: tuple[int, ...] = ()
    name_insignificant: tuple[bool, ...] = ()
    name: str = ""


@dataclass(frozen=True)
class OutlineGeometry(_ToDict):
    """A super-module box: the union of the visible modules below one parent module path.

    Attributes
    ----------
    path : str
        The parent module path, e.g. ``"1"`` or ``"1:2"``.
    level : int
        Its module level (``path`` has ``level`` components).
    max_level : int
        The deepest module level in its subtree (sets the web app's shadow/outline offset).
    x, y, width, height : float
        The raw union rect of the visible descendant modules (no render offset).
    order : int
        Index in the network's hierarchical draw order (breadth first, interleaved with the modules' ``order``).
    """

    path: str
    level: int
    max_level: int
    x: float
    y: float
    width: float
    height: float
    order: int


@dataclass(frozen=True)
class HighlightLabel(_ToDict):
    """One label of ``layout(highlight=...)``: its text, its highlight index (-1: drawn in the default color) and
    the color string registered for it.

    Examples
    --------
    >>> import alluvial
    >>> networks = [{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}]
    >>> geometry = alluvial.layout(networks, highlight={"group a": ["a"]}, highlight_colors=["tab:red"])
    >>> geometry.highlight_labels
    (HighlightLabel(label='group a', highlight_index=0, color='tab:red'),)
    """

    label: str
    highlight_index: int
    color: str


@dataclass(frozen=True)
class NetworkGeometry(_ToDict):
    """One network column. ``modules`` are the visible modules in layout order (bottom first). ``outlines`` are the
    super-module boxes of expanded modules in breadth-first order (empty when every module is a top module)."""

    id: str
    name: str
    index: int
    x: float
    y: float
    width: float
    height: float
    flow: float
    name_label: Label
    modules: tuple[ModuleGeometry, ...]
    outlines: tuple[OutlineGeometry, ...] = ()


@dataclass(frozen=True)
class StreamlineGeometry(_ToDict):
    """A streamline between two adjacent networks.

    Attributes
    ----------
    id : str
        The web app's link id (the left streamline node's id).
    left, right : tuple
        ``(network_index, module_id, highlight_index)`` of the group at each end.
    x0, y0, h0 : float
        Left end: x (module right edge), top y and height.
    x1, y1, h1 : float
        Right end: x (module left edge), top y and height.
    avg_height : float
        ``(h0 + h1) / 2``.
    highlight_index : int
        ``max(left_highlight_index, right_highlight_index)``; the draw-order key.
    left_insignificant, right_insignificant : bool
        Whether the group at each end is insignificant (drawn with a brighter color).
    """

    id: str
    left: tuple[int, str, int]
    right: tuple[int, str, int]
    x0: float
    y0: float
    h0: float
    x1: float
    y1: float
    h1: float
    avg_height: float
    highlight_index: int
    left_highlight_index: int
    right_highlight_index: int
    left_insignificant: bool = False
    right_insignificant: bool = False

    def _points(self) -> tuple[float, float, float, float, float, float, float]:
        y0 = 0.0 if self.y0 < SNAP_THRESHOLD else self.y0
        y1 = 0.0 if self.y1 < SNAP_THRESHOLD else self.y1
        y2 = y0 + self.h0
        y3 = y1 + self.h1
        cpx = (self.x0 + self.x1) / 2
        return self.x0, self.x1, y0, y1, y2, y3, cpx

    def path(self) -> list[tuple[int, tuple[float, float]]]:
        """Closed outline as ``(code, (x, y))`` pairs with matplotlib ``Path`` codes, in layout coordinates.

        Same points as the web app's SVG path: bottom edge left to right, up the right end, top edge back, close.
        Top edges below 1e-6 snap to 0.
        """
        x0, x1, y0, y1, y2, y3, cpx = self._points()
        return [
            (MOVETO, (x0, y2)),
            (CURVE4, (cpx, y2)),
            (CURVE4, (cpx, y3)),
            (CURVE4, (x1, y3)),
            (LINETO, (x1, y1)),
            (CURVE4, (cpx, y1)),
            (CURVE4, (cpx, y0)),
            (CURVE4, (x0, y0)),
            (CLOSEPOLY, (x0, y2)),
        ]

    def svg_path(self) -> str:
        """The SVG path string exactly as the web app formats it."""
        x0, x1, y0, y1, y2, y3, cpx = self._points()
        f = js_number_to_string
        return (
            f"M{f(x0)},{f(y2)}"
            f"C{f(cpx)},{f(y2)},{f(cpx)},{f(y3)},{f(x1)},{f(y3)}"
            f"L{f(x1)},{f(y1)}"
            f"C{f(cpx)},{f(y1)},{f(cpx)},{f(y0)},{f(x0)},{f(y0)}"
            "Z"
        )


@dataclass(frozen=True)
class AlluvialGeometry(_ToDict):
    """The complete diagram geometry.

    Attributes
    ----------
    width, height : float
        Diagram size in layout px.
    networks : tuple of NetworkGeometry
        Left to right.
    streamlines : tuple of StreamlineGeometry
        In draw order (``getLinks`` order per network pair, pairs left to right).
    palette : tuple of str
        The highlight colors in effect; ``highlight_index`` i maps to ``palette[i]``.
    options : LayoutOptions or None
        The options the layout ran with.
    highlight_labels : tuple of HighlightLabel
        The labels of ``layout(highlight=...)`` in label order (empty otherwise), for legends.

    Examples
    --------
    >>> import alluvial
    >>> geometry = alluvial.layout([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], names=["2020", "2021"])
    >>> geometry.width, geometry.height
    (320.0, 600.0)
    >>> module = geometry.networks[0].modules[0]
    >>> module.id, module.label.text.splitlines()
    ('1', ['a', 'b'])

    It converts to plain dicts and lists (e.g. for JSON) and back:

    >>> alluvial.AlluvialGeometry.from_dict(geometry.to_dict()) == geometry
    True
    """

    width: float
    height: float
    networks: tuple[NetworkGeometry, ...]
    streamlines: tuple[StreamlineGeometry, ...]
    palette: tuple[str, ...] = ()
    options: LayoutOptions | None = field(default=None)
    highlight_labels: tuple[HighlightLabel, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlluvialGeometry:
        """Inverse of ``to_dict()``."""
        from .layout import LayoutOptions

        def label(d: dict[str, Any] | None) -> Label | None:
            return None if d is None else Label(**d)

        networks = []
        for n in data["networks"]:
            modules = tuple(
                ModuleGeometry(
                    **{
                        **m,
                        "path": tuple(m["path"]),
                        "groups": tuple(GroupGeometry(**g) for g in m["groups"]),
                        "label": label(m["label"]),
                        "largest_leaf_names": tuple(m["largest_leaf_names"]),
                        "name_candidates": tuple(m.get("name_candidates", ())),
                        "name_highlight_indices": tuple(m.get("name_highlight_indices", ())),
                        "name_insignificant": tuple(m.get("name_insignificant", ())),
                    }
                )
                for m in n["modules"]
            )
            outlines = tuple(OutlineGeometry(**o) for o in n.get("outlines", ()))
            networks.append(
                NetworkGeometry(
                    **{**n, "name_label": label(n["name_label"]), "modules": modules, "outlines": outlines}
                )
            )
        streamlines = tuple(
            StreamlineGeometry(**{**s, "left": tuple(s["left"]), "right": tuple(s["right"])})
            for s in data["streamlines"]
        )
        options = data.get("options")
        return cls(
            width=data["width"],
            height=data["height"],
            networks=tuple(networks),
            streamlines=streamlines,
            palette=tuple(data.get("palette", ())),
            options=None if options is None else LayoutOptions(**options),
            highlight_labels=tuple(HighlightLabel(**h) for h in data.get("highlight_labels", ())),
        )


def js_ceil(x: float) -> float:
    """``Math.ceil``: NaN and infinities pass through (``math.ceil`` raises), and results beyond 2**53 stay
    floats, so parity and odd/even checks behave like JS (a NaN module height gives no label names)."""
    if not math.isfinite(x):
        return x
    c = math.ceil(x)
    return c if -(2**53) <= c <= 2**53 else float(c)


def build_geometry(
    diagram: Any,
    options: LayoutOptions,
    *,
    palette: tuple[str, ...] = (),
    font_size: float = 8.0,
    aggregate_state_names: bool = True,
    highlight_labels: tuple[HighlightLabel, ...] = (),
) -> AlluvialGeometry:
    """Snapshot a laid-out engine diagram into an ``AlluvialGeometry``.

    Contract: ``diagram`` is an ``alluvial.engine`` Diagram on which ``calc_flow`` and ``update_layout(options)``
    have run (and any color operations, each followed by its own layout). The result holds, per network in
    ``diagram.children`` order, the visible modules in ``network.children`` order with their groups (module
    ``children`` order) and labels (layout.md §6, colors-render.md §7.5), and the streamlines of
    ``network.get_links(options.streamline_threshold)`` for each network pair, left to right. All numbers are
    copied unchanged from the engine. ``palette`` is the store's ``highlightColors``.

    Parameters
    ----------
    font_size : float, default 8
        Module label font size (TS ``fontSize``); sets how many leaf names fit a module
        (``ceil(height / (1.8 * font_size))``, made odd).
    aggregate_state_names : bool, default True
        Sum state-node flows per physical node for the label names (TS ``aggregateStateNames``).
    highlight_labels : tuple of HighlightLabel
        Copied to ``AlluvialGeometry.highlight_labels``.

    The hierarchy (``ModuleGeometry.level``/``order``, ``NetworkGeometry.outlines``) comes from TS
    ``network.hierarchicalChildren`` (v2-hierarchy.md §8, §11). A module shown together with one of its
    sub-modules (reachable only through input module levels) gets one outline enclosing both (fix round E15a).
    """
    networks = []
    streamlines = []
    network_index = {id(network): i for i, network in enumerate(diagram.children)}
    height_per_line = font_size * 1.8

    for i, network in enumerate(diagram.children):
        outlines, order = _hierarchy(network)
        modules = []
        for module in network.children:
            if not module.is_visible:
                continue
            groups = tuple(
                GroupGeometry(
                    highlight_index=g.highlight_index,
                    insignificant=g.insignificant,
                    x=g.x,
                    y=g.y,
                    width=g.width,
                    height=g.height,
                    flow=g.flow,
                )
                for g in module.children
            )
            max_lines = js_ceil(module.height / height_per_line)
            if max_lines != 0 and max_lines % 2 == 0:
                max_lines -= 1
            names: tuple[str, ...] = ()
            name_nodes: list[Any] = []
            if max_lines > 0:
                name_nodes = module.get_largest_leaf_nodes(max_lines, aggregate_state_names)
                names = tuple("" if node.name is None else str(node.name) for node in name_nodes)
            anchor = module.text_anchor
            label = None
            candidates: tuple[str, ...] = ()
            if anchor is not None and names:
                x, y = module.name_position
                label = Label("\n".join(names), x, y, anchor, math.ceil(len(names) / 2) - 1)
                candidates = names
                if len(names) < NAME_CANDIDATES:
                    # Keep the parity names as the exact prefix; append the rest of a larger query.
                    rest = Counter(names)
                    extra = []
                    extra_nodes = []
                    for node in module.get_largest_leaf_nodes(NAME_CANDIDATES, aggregate_state_names):
                        name = "" if node.name is None else str(node.name)
                        if rest[name]:
                            rest[name] -= 1
                        else:
                            extra.append(name)
                            extra_nodes.append(node)
                    candidates = (names + tuple(extra))[:NAME_CANDIDATES]
                    name_nodes = (name_nodes + extra_nodes)[:NAME_CANDIDATES]
            modules.append(
                ModuleGeometry(
                    id=module.module_id,
                    path=tuple(module.path),
                    network_index=i,
                    flow=module.flow,
                    x=module.x,
                    y=module.y,
                    width=module.width,
                    height=module.height,
                    highlight_index=module.highlight_index,
                    groups=groups,
                    label=label,
                    largest_leaf_names=names,
                    name_candidates=candidates,
                    level=module.module_level,
                    max_level=module.max_module_level,
                    order=order.get(id(module), len(modules)),
                    name_highlight_indices=tuple(node.highlight_index for node in name_nodes),
                    name_insignificant=tuple(
                        bool(getattr(node, "insignificant", False)) for node in name_nodes
                    ),
                    name=module.name or "",
                )
            )
        name = "" if network.name is None else str(network.name)
        nx, ny = network.name_position
        networks.append(
            NetworkGeometry(
                id=network.network_id,
                name=name,
                index=i,
                x=network.x,
                y=network.y,
                width=network.width,
                height=network.height,
                flow=network.flow,
                name_label=Label(name, nx, ny, "middle"),
                modules=tuple(modules),
                outlines=outlines,
            )
        )
        for link in network.get_links(options.streamline_threshold):
            left, right = link.left, link.right
            left_group, right_group = left.parent.parent, right.parent.parent
            streamlines.append(
                StreamlineGeometry(
                    id=link.id,
                    left=(
                        network_index[id(left_group.parent.parent)],
                        left_group.parent.module_id,
                        left_group.highlight_index,
                    ),
                    right=(
                        network_index[id(right_group.parent.parent)],
                        right_group.parent.module_id,
                        right_group.highlight_index,
                    ),
                    x0=link.x0,
                    y0=link.y0,
                    h0=link.h0,
                    x1=link.x1,
                    y1=link.y1,
                    h1=link.h1,
                    avg_height=link.avg_height,
                    highlight_index=link.highlight_index,
                    left_highlight_index=link.left_highlight_index,
                    right_highlight_index=link.right_highlight_index,
                    left_insignificant=left_group.insignificant,
                    right_insignificant=right_group.insignificant,
                )
            )

    return AlluvialGeometry(
        width=diagram.width,
        height=diagram.height,
        networks=tuple(networks),
        streamlines=tuple(streamlines),
        palette=tuple(palette),
        options=options,
        highlight_labels=tuple(highlight_labels),
    )


def _hierarchy(network: Any) -> tuple[tuple[OutlineGeometry, ...], dict[int, int]]:
    """Outlines (non-leaf ``TreeNode``s) and ``id(module) -> order`` from ``network.hierarchical_children``."""
    from .engine.network import TreeNode

    items = network.hierarchical_children
    outlines = []
    order: dict[int, int] = {}
    for k, item in enumerate(items):
        if isinstance(item, TreeNode):
            outlines.append(
                OutlineGeometry(
                    path=item.path,
                    level=item.module_level,
                    max_level=item.max_module_level,
                    x=item.x,
                    y=item.y,
                    width=item.width,
                    height=item.height,
                    order=k,
                )
            )
        else:
            order[id(item)] = k
    return tuple(outlines), order
