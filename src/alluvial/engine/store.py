"""The slice of ``store/DiagramStore.ts`` the layout needs: building the diagram, relayout, the color and highlight
operations with the TS mutation quirks (spec: docs/dev/port-notes/colors-render.md §2, §4, §6 and v2-highlight.md §2-§4),
and the hierarchy operations (expand, regroup, move, reset; v2-hierarchy.md §6, §10).

Every operation ends with ``calc_flow`` + ``update_layout`` on the same diagram, as in the store, except
``move_module`` (layout without ``calc_flow``, as TS ``moveSelectedModule``).
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from .._jscompat import is_array_index_key, js_is_integer, js_number_to_string, js_truthy
from .._palette import (
    DEFAULT_HIGHLIGHT_COLOR,
    DEFAULT_TONE,
    check_offset,
    check_tone,
    hierarchy_options,
    scheme_colors,
)
from ..io.alluvial_format import (
    DISPLAY_OPTION_DEFAULTS,
    LAYOUT_OPTION_KEYS,
    SAVED_OPTION_KEYS,
    AlluvialRestore,
    read_alluvial_metadata,
)
from ._utils import sort_by_number
from .diagram import Diagram, LayoutTrace
from .highlight_group import NOT_HIGHLIGHTED
from .side import LEFT, RIGHT

if TYPE_CHECKING:
    from ..io.types import NetworkFile
    from ..layout import LayoutOptions
    from .leaf_node import LeafNode
    from .module import Module
    from .network import Network

#: Private metadata key of the ``highlight`` path (v2-highlight.md §7.1); cannot collide with user metadata names.
HIGHLIGHT_KEY = "\x00alluvial.highlight"

#: Store ops that can be refused (they return a bool; TS logs a warning and changes nothing).
REFUSABLE_OPS = frozenset({"expand", "regroup", "moveModule"})

_NAN_KEY = object()


def _same_value_zero_key(value: Any) -> Any:
    """A JS ``Map`` key: primitives by value (SameValueZero, booleans apart from numbers), objects by identity."""
    if value is None or isinstance(value, (bool, str)):
        return (type(value).__name__, value)
    if isinstance(value, (int, float)):
        return ("number", _map_key(value) if isinstance(value, float) else value)
    return ("object", id(value))


def _map_key(value: Any) -> Any:
    """A JS ``Map`` key (SameValueZero): all NaNs are one key."""
    return _NAN_KEY if isinstance(value, float) and math.isnan(value) else value


def _is_js_number(value: Any) -> bool:
    """``typeof value === "number"``."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _have_metadata(network: Network) -> bool:
    """TS ``network.haveMetadata``: some leaf has metadata (False for a network without leaves)."""
    return network.have_metadata


def _metadata_value(node: LeafNode, name: str) -> Any:
    """``node.metadata[name]`` when TS would read it (``!node.metadata || !(name in node.metadata)`` skip), else a
    sentinel.

    Falsy metadata (``null``, ``false``, ``0``, NaN, ``""``) is skipped. An array (JSON list) has its index keys and
    ``length``; its prototype methods are functions, which every caller skips. Other truthy primitives make the
    ``in`` operator throw, as in TS.
    """
    md = node.metadata
    if not js_truthy(md):
        return _MISSING
    if isinstance(md, Mapping):
        return md.get(name, _MISSING)
    if isinstance(md, (list, tuple)):
        if name == "length":
            return len(md)
        if is_array_index_key(name) and int(name) < len(md):
            return md[int(name)]
        return _MISSING
    shown = "true" if md is True else js_number_to_string(md) if isinstance(md, (int, float)) else str(md)
    raise TypeError(f"Cannot use 'in' operator to search for '{name}' in {shown}")


_MISSING = object()


def _js_get(items: Sequence[Any], index: int) -> Any:
    """JS ``array[index]``: ``undefined`` (None) out of range, including negative indices."""
    return items[index] if 0 <= index < len(items) else None


class DiagramStore:
    """Holds the diagram, the layout options and the highlight color registry (TS ``highlightColors``).

    Parameters
    ----------
    options : LayoutOptions
        Layout options passed to every ``update_layout``.
    scheme : str or sequence of str, optional
        Color scheme for the coloring operations: a web-app scheme name (``alluvial.SCHEMES``, TS ctor
        option ``colorScheme``) or a list of colors. Default ``"C3 Sinebow"``.
    tone : str, optional
        The c3 tone of the C3 schemes and of ``color_module_hierarchy_in_all_networks`` (``_palette.TONES``,
        TS ctor option ``colorTone``). Default ``"strong"``.
    offset : float or None, optional
        The c3 offset of the first color, in degrees around the hue source (TS ctor option ``colorOffset``).
        Default ``None``, c3's default for the scheme.
    default_highlight_color : str, optional
        Color of ``highlight_index == -1``.
    show_bipartite_nodes : bool, default True
        TS ``showBipartiteNodes``: ``False`` hides the nodes of a bipartite network's second type (node id >=
        ``bipartiteStartId``), applied when the diagram is built (fix round E19).
    display_options : mapping, optional
        The TS store's display options that do not affect the layout
        (``alluvial.io.alluvial_format.DISPLAY_OPTION_DEFAULTS`` keys, TS names); kept so that a saved diagram writes
        them back.
    trace : callable, optional
        Forwarded to ``Diagram.update_layout`` (test instrumentation).
    """

    def __init__(
        self,
        options: LayoutOptions,
        *,
        scheme: str | Sequence[str] = "C3 Sinebow",
        tone: str = DEFAULT_TONE,
        offset: float | None = None,
        default_highlight_color: str = DEFAULT_HIGHLIGHT_COLOR,
        show_bipartite_nodes: bool = True,
        display_options: Mapping[str, Any] | None = None,
        trace: LayoutTrace | None = None,
    ) -> None:
        self.options = options
        self.selected_scheme_name: str | None = None
        self.selected_scheme: list[str] = []
        self.selected_tone: str = check_tone(tone)
        # None for c3's default offset of the scheme
        self.selected_offset: float | None = check_offset(offset)
        self._set_scheme(scheme)
        self.default_highlight_color = default_highlight_color
        self.show_bipartite_nodes = show_bipartite_nodes
        self.display_options: dict[str, Any] = dict(DISPLAY_OPTION_DEFAULTS)
        if display_options:
            unknown = set(display_options) - set(DISPLAY_OPTION_DEFAULTS)
            if unknown:
                raise ValueError(f"unknown display options {sorted(unknown)}")
            self.display_options.update(display_options)
        self.highlight_colors: list[Any] = list(self.selected_scheme)
        self.diagram = Diagram()
        self.networks: list[NetworkFile] = []
        self.trace = trace
        self.update_layout_calls = 0

    def check_colors(self, networks: Sequence[NetworkFile]) -> None:
        """TS ``checkColors`` (v2-io.md §4, v3-webapp-json.md §5): the palette from the files' ``colors``.

        The files' palettes are merged into one registry (first occurrence wins). A list palette is local to its file:
        each node's ``highlight_index`` into it is remapped to the merged index (an index outside the file's palette,
        ``-1`` or past the end, is kept), and the file's ``colors`` becomes the merged palette, so a second call on the
        same files is the identity. ``colors: true`` sets each node's ``highlight_index`` from its ``color``. Both
        mutate the files and nodes, as in TS. Then ``highlight_colors`` is replaced (``[]`` if no file has colors).
        """
        colors: list[Any] = []
        color_indices: dict[Any, int] = {}

        def register(color: Any) -> int:
            key = _same_value_zero_key(color)
            index = color_indices.get(key)
            if index is None:
                colors.append(color)
                index = color_indices[key] = len(colors) - 1
            return index

        array_palettes = []
        for network in networks:
            file_colors = getattr(network, "colors", None)
            if isinstance(file_colors, list):
                merged = [register(color) for color in file_colors]
                for node in network.nodes or ():
                    local = getattr(node, "highlight_index", None)
                    if js_is_integer(local) and 0 <= local < len(merged):
                        node.highlight_index = merged[int(local)]
                array_palettes.append(network)
            elif file_colors is True:
                for node in network.nodes or ():
                    color = getattr(node, "color", None)
                    if color is not None:
                        node.highlight_index = register(color)
        for network in array_palettes:
            network.colors = list(colors)
        self.set_highlight_colors(colors)

    def set_networks(self, networks: Sequence[NetworkFile]) -> None:
        self.check_colors(networks)
        self.networks = list(networks)
        self.diagram = Diagram(networks)
        # E19: hide the bipartite nodes before the first layout when the option says so
        for network in self.diagram.children:
            network.toggle_show_bipartite_nodes(self.show_bipartite_nodes)
        self.update_layout()

    def set_show_bipartite_nodes(self, show: bool) -> None:
        """TS ``setShowBipartiteNodes``: show or hide the second node type of the bipartite networks, then lay out."""
        self.show_bipartite_nodes = show
        for network in self.diagram.children:
            if network.is_bipartite:
                network.toggle_show_bipartite_nodes(show)
        self.update_layout()

    def get_options(self) -> dict[str, Any]:
        """TS ``getOptions``: the options a saved diagram stores, under their TS names, in ``SAVED_OPTION_KEYS``
        order (layout options, ``defaultHighlightColor``, ``showBipartiteNodes`` and the display options)."""
        values = {
            **self.display_options,
            **self.options.to_ts(),
            "defaultHighlightColor": self.default_highlight_color,
            "showBipartiteNodes": self.show_bipartite_nodes,
        }
        return {key: values[key] for key in SAVED_OPTION_KEYS}

    def restore_options(self, options: Mapping[str, Any]) -> None:
        """Assign saved options (TS names, checked by ``read_alluvial_metadata``) without a layout."""
        from ..layout import LayoutOptions

        layout = {k: v for k, v in options.items() if k in LAYOUT_OPTION_KEYS}
        if layout:
            self.options = LayoutOptions.from_ts({**self.options.to_ts(), **layout})
        for key, value in options.items():
            if key == "defaultHighlightColor":
                self.default_highlight_color = value
            elif key == "showBipartiteNodes":
                self.show_bipartite_nodes = value
            elif key in DISPLAY_OPTION_DEFAULTS:
                self.display_options[key] = value

    def open_networks(self, networks: Sequence[NetworkFile]) -> list[str]:
        """TS ``openNetworks``: open the files of a saved diagram (or any network files).

        Restores the saved options and scheme (no layout), builds the diagram (``set_networks``), then restores the
        custom module orders (``set_module_order``: at most one layout, no ``calc_flow``) and the module names.
        Files without a saved block load as with ``set_networks``. The saved blocks are consumed: they are removed
        from the files once read (``alluvial = None``), so opening the same files again keeps the current state
        instead of restoring the save a second time. Returns the warnings for what could not be restored (the TS
        text).
        """
        saved = read_alluvial_metadata(networks)
        for file in networks:
            file.alluvial = None
        warnings_ = list(saved.warnings)
        if saved.options is not None:
            self.restore_options(saved.options)
            self.restore_saved_scheme(saved)
        self.set_networks(networks)
        self.restore_saved_order_and_names(saved, warnings_)
        return warnings_

    def restore_saved_scheme(self, saved: AlluvialRestore) -> None:
        """The scheme step of ``open_networks`` (TS, #57): a saved scheme other than the current one replaces it and
        resets the offset; then the saved tone and offset apply when present (missing ones keep the current); the
        scheme colors are recomputed. No layout."""
        if saved.color_scheme is not None and saved.color_scheme != self.selected_scheme_name:
            self.selected_scheme_name = saved.color_scheme
            # The default offset differs between hue sources
            self.selected_offset = None
        if saved.color_tone is not None:
            self.selected_tone = saved.color_tone
        if saved.has_color_offset:
            self.selected_offset = saved.color_offset
        self._update_scheme_colors()

    def restore_saved_order_and_names(
        self, saved: AlluvialRestore, warnings_: list[str], *, order: bool = True, names: bool = True
    ) -> None:
        """The module-order and module-name steps of ``open_networks`` (appends to ``warnings_``)."""
        networks = self.diagram.children
        if order:
            orders = []
            for network, block in zip(networks, saved.networks, strict=False):
                module_order = block.get("moduleOrder") if block else None
                if module_order is None:
                    continue
                modules = []
                for module_id in module_order:
                    module = network.get_module(module_id)
                    if module is not None:
                        modules.append(module)
                    else:
                        warnings_.append(
                            f"{network.name}: module {module_id} of the saved module order does not exist"
                        )
                orders.append((network, modules))
            if orders:
                self.set_module_order(orders)
        if names:
            for network, block in zip(networks, saved.networks, strict=False):
                for module_id, name in ((block or {}).get("moduleNames") or {}).items():
                    module = network.get_module(module_id)
                    if module is not None:
                        module.name = name
                    else:
                        warnings_.append(
                            f"{network.name}: module {module_id} of the saved module names does not exist"
                        )

    def update_layout(self) -> None:
        if len(self.diagram.children) == 0:
            return
        self.diagram.calc_flow()
        self.diagram.update_layout(self.options, self.trace)
        self.update_layout_calls += 1

    def get_highlight_index(self, highlight_color: Any) -> int:
        if highlight_color == self.default_highlight_color:
            return NOT_HIGHLIGHTED
        colors = self.highlight_colors
        if highlight_color in colors:
            return colors.index(highlight_color)
        colors.append(highlight_color)
        return len(colors) - 1

    def _scheme_color(self, i: int) -> str:
        return self.selected_scheme[i % len(self.selected_scheme)]

    def color_module(self, module: Module, color: Any, update_layout: bool = True) -> None:
        highlight_index = self.get_highlight_index(color)
        module.set_color(highlight_index)
        if update_layout:
            self.update_layout()

    def color_matching_modules_in_all_networks(self) -> None:
        if len(self.diagram.children) == 0:
            return

        self.clear_colors(False)

        networks = self.diagram.children

        if len(networks) < 2:
            children = networks[0].children
            for i in range(len(children)):
                self.color_module(children[i], self._scheme_color(i), False)
            self.update_layout()
            return

        highlight_index = 0  # one counter for all network pairs (S1)
        for i in range(len(networks) - 1):
            left_network = networks[i]
            links: dict[Module, dict[Module, float]] = {}

            j = 0
            while j < len(left_network.children):
                module = left_network.children[j]
                for match in module.get_similar_modules(RIGHT, 1):
                    links.setdefault(module, {})[match.module] = match.similarity
                j += 1

            for left, rights in links.items():
                if left.is_highlighted:
                    color = _js_get(self.highlight_colors, left.highlight_index)
                else:
                    largest_link: Any = None
                    largest_flow = float("-inf")
                    for module in rights:
                        if module.is_highlighted and largest_flow < module.flow:
                            largest_link = module
                            largest_flow = module.flow

                    if largest_link is not None:
                        color = _js_get(self.highlight_colors, largest_link.highlight_index)
                    else:
                        color = self._scheme_color(highlight_index)

                    self.color_module(left, color, False)
                    highlight_index += 1

                for right in rights:
                    if not right.is_highlighted:
                        self.color_module(right, color, False)

        self.update_layout()

    def color_nodes_in_module(self, module: Module, color: Any, update_layout: bool = True) -> None:
        highlight_index = self.get_highlight_index(color)
        module.set_color(highlight_index)

        for network in [n for n in self.diagram.children if n.network_id != module.network_id]:
            nodes = []
            for node in module.get_leaf_nodes():
                opposite_node = network.get_leaf_node(node.identifier)
                if opposite_node is not None and opposite_node.highlight_index != highlight_index:
                    opposite_node.highlight_index = highlight_index
                    nodes.append(opposite_node)
            for node in nodes:
                node.update()

        if update_layout:
            self.update_layout()

    def color_nodes_in_modules_in_all_networks(self, network_id: str | None = None) -> None:
        if len(self.diagram.children) == 0:
            return

        self.clear_colors(False)

        network = self.diagram.get_network(
            network_id if network_id is not None else self.diagram.children[0].network_id
        )

        if network is not None:
            for i, module in enumerate([m for m in network.children if m.is_visible]):
                self.color_nodes_in_module(module, self._scheme_color(i), False)

        self.update_layout()

    def color_module_ids_in_all_networks(self) -> None:
        self.clear_colors(False)
        module_id_color_map: dict[str, str] = {}

        def set_module_color(module: Module) -> None:
            color = module_id_color_map.get(module.module_id)
            if color:
                module.set_color(self.get_highlight_index(color))
            else:
                color = self._scheme_color(len(module_id_color_map))
                module_id_color_map[module.module_id] = color
                module.set_color(self.get_highlight_index(color))

        networks = self.diagram.children
        multilayer_network_id = networks[0].original_id if networks else None
        if all(n.layer_id is not None and n.original_id == multilayer_network_id for n in networks):
            modules_by_id: dict[str, dict[str, Any]] = {}
            for network in networks:
                children = network.children
                for i in range(len(children)):
                    module = children[i]
                    if module.is_visible:
                        entry = modules_by_id.setdefault(module.module_id, {"flow": 0, "modules": []})
                        entry["flow"] = entry["flow"] + module.flow
                        entry["modules"].append(module)
            groups = list(modules_by_id.values())  # TS Map: insertion order
            sort_by_number(groups, lambda e: e["flow"], descending=True)
            for entry in groups:
                for module in entry["modules"]:
                    set_module_color(module)
        else:
            for network in networks:
                children = network.children
                for i in range(len(children)):
                    module = children[i]
                    if module.is_visible:
                        set_module_color(module)

        self.update_layout()

    def color_module_hierarchy_in_all_networks(self) -> None:
        """TS ``colorModuleHierarchyInAllNetworks``: color the visible modules by their place in the module
        hierarchy with c3's ``hierarchy()``, so that sub-modules get colors close to their parent; the same module
        path gets the same color in all networks.

        The scheme, tone and offset set the colors of the top modules (``_palette.hierarchy_options``); a
        list scheme is taken as c3 seeds, like the schemes that are no hue source.
        """
        if len(self.diagram.children) == 0:
            return
        import c3

        # Clearing colors can replace modules, and leaves their flows stale until the next layout, so remember
        # which modules were visible by id
        visible_module_ids = {
            module.id for network in self.diagram.children for module in network.children if module.is_visible
        }

        self.clear_colors(False)

        # One entry per node, c3 sums the flow of each module path
        modules: list[dict[str, Any]] = []
        for network in self.diagram.children:
            for node in network.leaf_nodes():
                path = node.tree_path.to_array()
                modules.append({"path": path[:-1] if len(path) > 1 else path, "flow": node.flow})

        if self.selected_scheme_name is not None:
            options = hierarchy_options(self.selected_scheme_name, self.selected_tone, self.selected_offset)
        else:
            options = {"seeds": tuple(self.selected_scheme)}
        color = c3.hierarchy(modules, **options)

        visible = [
            module
            for network in self.diagram.children
            for module in network.children
            if module.id in visible_module_ids
        ]
        for module in visible:
            self.color_module(module, color(module.path), False)

        self.update_layout()

    def clear_colors(self, update_layout: bool = True) -> None:
        for network in self.diagram.children:
            modules = [m for m in network.children if any(g.is_highlighted for g in m.children)]
            for module in modules:
                module.remove_colors()

        self.highlight_colors = []

        if update_layout:
            self.update_layout()

    def set_option(self, key: str, value: Any) -> None:
        """A store option setter (``setHeight``, ``setFlowThreshold``, ...; ``key`` is the TS option name):
        replace the option and run one ``update_layout`` on the same diagram."""
        from ..layout import LayoutOptions

        self.options = LayoutOptions.from_ts({**self.options.to_ts(), key: value})
        self.update_layout()

    # --- registry management (v2-highlight.md §4) ---------------------------------------------------------------

    def set_highlight_colors(self, highlight_colors: Sequence[Any]) -> None:
        """Replace the registry; touches no leaf and runs no layout."""
        self.highlight_colors = list(highlight_colors)

    def set_default_highlight_color(self, color: str) -> None:
        """Change the color of index -1 (affects later ``get_highlight_index`` calls only; no layout)."""
        self.default_highlight_color = color

    def set_selected_scheme(self, scheme: str | Sequence[str]) -> None:
        """The scheme for later color ops (no recoloring): a web-app scheme name or a list of colors.

        Resets the offset to c3's default (``None``), whose value differs between hue sources, and keeps the tone
        (TS ``setSelectedScheme``)."""
        # The default offset differs between hue sources
        self.selected_offset = None
        self._set_scheme(scheme)

    def set_selected_tone(self, tone: str) -> None:
        """TS ``setSelectedTone``: the c3 tone of the C3 schemes and of the hierarchy coloring (no recoloring)."""
        self.selected_tone = check_tone(tone)
        self._update_scheme_colors()

    def set_selected_offset(self, offset: float | None) -> None:
        """TS ``setSelectedOffset``: the c3 offset of the first color, in degrees around the hue source (no
        recoloring). ``None`` (c3's default) is a Python extension; the TS setter takes a number."""
        self.selected_offset = check_offset(offset)
        self._update_scheme_colors()

    def _set_scheme(self, scheme: str | Sequence[str]) -> None:
        if isinstance(scheme, str):
            colors = list(scheme_colors(scheme, self.selected_tone, self.selected_offset))
            self.selected_scheme_name = scheme
            self.selected_scheme = colors
        else:
            colors = list(scheme)
            if not colors:
                raise ValueError("a color scheme needs at least one color")
            self.selected_scheme = colors
            self.selected_scheme_name = None

    def _update_scheme_colors(self) -> None:
        """TS ``selectedScheme = schemeColors(selectedSchemeName, selectedTone, selectedOffset)``; a list scheme
        (``selected_scheme_name`` None) does not change."""
        if self.selected_scheme_name is not None:
            self.selected_scheme = list(
                scheme_colors(self.selected_scheme_name, self.selected_tone, self.selected_offset)
            )

    def set_network_name(self, network_id: str, name: str) -> None:
        """TS ``setNetworkName``: rename the diagram network (not the file); no layout."""
        network = self.diagram.get_network(network_id)
        if network is not None:
            network.name = name

    def set_module_name(self, module: Module, name: str) -> None:
        """TS ``setModuleName``: the module's custom name; no layout."""
        module.name = name

    def get_highlight_color(
        self, highlight_index: int | None, default_highlight_color: str | None = None
    ) -> Any:
        if highlight_index is None or highlight_index > len(self.highlight_colors) - 1:
            return None
        if highlight_index == NOT_HIGHLIGHTED:
            return (
                default_highlight_color
                if default_highlight_color is not None
                else self.default_highlight_color
            )
        return _js_get(self.highlight_colors, highlight_index)

    # --- v2 color ops (v2-highlight.md §3) ----------------------------------------------------------------------

    def color_matching_modules(self, module: Module, color: Any, side: int | None = None) -> None:
        highlight_index = self.get_highlight_index(color)
        module.set_color(highlight_index)

        if not side or side == LEFT:
            left = module.get_similar_modules(LEFT)
            if left:
                self.color_matching_modules(left[0].module, color, LEFT)

        if not side or side == RIGHT:
            right = module.get_similar_modules(RIGHT)
            if right:
                self.color_matching_modules(right[0].module, color, RIGHT)

        if not side:
            self.update_layout()

    def color_selected_nodes(self, nodes: Iterable[LeafNode], color: Any) -> None:
        highlight_index = self.get_highlight_index(color)
        for node in nodes:
            if node.highlight_index != highlight_index:
                node.highlight_index = highlight_index
                node.update()
            for network in self.diagram.children:
                if network.network_id == node.network_id:
                    continue
                other = network.get_leaf_node(node.identifier)
                if other is None or other.highlight_index == highlight_index:
                    continue
                other.highlight_index = highlight_index
                other.update()
        self.update_layout()

    def color_module_ids(self, module: Module, color: Any) -> None:
        highlight_index = self.get_highlight_index(color)
        module.set_color(highlight_index)
        module_id = module.module_id
        for network in [n for n in self.diagram.children if n.network_id != module.network_id]:
            children = network.children
            for i in range(len(children)):  # JS forEach: length fixed, elements read live
                other = children[i]
                if other.is_visible and other.module_id == module_id:
                    other.set_color(highlight_index)
        self.update_layout()

    def _visible_leaf_walk(
        self, network_filter: Callable[[Network], bool], visit: Callable[[LeafNode], None]
    ) -> None:
        """The walk of the layer/physical-id/metadata ops: every leaf of every visible module, leaves snapshotted
        per module. Recoloring keeps every module in place (E4), so ``network.children`` does not change."""
        for network in self.diagram.children:
            if not network_filter(network):
                continue
            for module in network.children:
                if not module.is_visible:
                    continue
                for node in module.get_leaf_nodes():
                    visit(node)

    def _color_by_key(self, key: Callable[[LeafNode], Any], skip_none: bool) -> None:
        key_color: dict[Any, str] = {}

        def visit(node: LeafNode) -> None:
            value = key(node)
            if skip_none and value is None:
                return
            k = _map_key(value)
            if k not in key_color:
                key_color[k] = self._scheme_color(len(key_color))
            highlight_index = self.get_highlight_index(key_color[k])
            if node.highlight_index != highlight_index:
                node.highlight_index = highlight_index
                node.update()

        self._visible_leaf_walk(lambda network: True, visit)
        self.update_layout()

    def color_by_layer(self) -> None:
        self._color_by_key(lambda node: node.layer_id, True)

    def color_by_physical_id(self) -> None:
        self._color_by_key(lambda node: node.node_id, False)

    def color_categorical_metadata(self, name: str, colors: Mapping[Any, Any]) -> None:
        """``colors`` maps category (str) to color, in JS ``Map`` order (= highlight index order)."""
        self.clear_colors(False)
        for color in colors.values():
            self.get_highlight_index(color)

        def visit(node: LeafNode) -> None:
            meta = _metadata_value(node, name)
            if meta is _MISSING or not isinstance(meta, str):
                return
            if meta in colors:
                highlight_index = self.get_highlight_index(colors[meta])
                if node.highlight_index != highlight_index:
                    node.highlight_index = highlight_index
                    node.update()

        self._visible_leaf_walk(_have_metadata, visit)
        self.update_layout()

    def color_real_metadata(self, name: str, bins: Sequence[Mapping[str, Any]]) -> None:
        """``bins``: ``{"x0", "x1", "color"}`` records; a value takes the first bin with ``x0 <= v < x1``, or
        ``x0 <= v <= x1`` for the last bin (S6: the data maximum gets the last color)."""
        self.clear_colors(False)
        for b in bins:
            self.get_highlight_index(b["color"])

        def visit(node: LeafNode) -> None:
            meta = _metadata_value(node, name)
            if meta is _MISSING or not _is_js_number(meta):
                return
            for k, b in enumerate(bins):
                if meta >= b["x0"] and (meta < b["x1"] or (k == len(bins) - 1 and meta == b["x1"])):
                    highlight_index = self.get_highlight_index(b["color"])
                    if node.highlight_index != highlight_index:
                        node.highlight_index = highlight_index
                        node.update()
                    break

        self._visible_leaf_walk(_have_metadata, visit)
        self.update_layout()

    def color_real_intervals(
        self, name: str, data: Any, get_color: Callable[[float], Any], centers: Sequence[float]
    ) -> None:
        """``data`` is unused (as in TS)."""
        self.clear_colors(False)
        for c in centers:
            self.get_highlight_index(get_color(c))

        def visit(node: LeafNode) -> None:
            meta = _metadata_value(node, name)
            if meta is _MISSING or not _is_js_number(meta):
                return
            highlight_index = self.get_highlight_index(get_color(meta))
            if node.highlight_index != highlight_index:
                node.highlight_index = highlight_index
                node.update()

        self._visible_leaf_walk(_have_metadata, visit)
        self.update_layout()

    # --- hierarchy (v2-hierarchy.md §6.1) ------------------------------------------------------------------------

    def expand(self, module: Module) -> bool:
        if not module.expand():
            return False
        self.update_layout()
        return True

    def regroup(self, module: Module) -> bool:
        if not module.regroup():
            return False
        self.update_layout()
        return True

    def move_module(self, module: Module, direction: str) -> bool:
        """TS ``moveSelectedModule`` with the module passed in: lays out **without** ``calc_flow``."""
        if not module.move(direction):
            return False
        self.diagram.update_layout(self.options, self.trace)
        self.update_layout_calls += 1
        return True

    def set_module_order(self, orders: Sequence[tuple[Network, Sequence[Module]]]) -> bool:
        """TS ``setModuleOrder`` (fix round B1): ``Network.set_module_order`` for each listed network (each is
        frozen), then, if some ``children`` order changed, one layout without ``calc_flow`` (flows do not change)."""
        changed = False
        for network, modules in orders:
            changed = network.set_module_order(modules) or changed
        if changed:
            self.diagram.update_layout(self.options, self.trace)
            self.update_layout_calls += 1
        return changed

    def reset_layout(self) -> None:
        for network in self.diagram.children:
            network.is_custom_sorted = False
        self.update_layout()

    def _levels(self, levels: int | Sequence[int]) -> list[int]:
        n = len(self.diagram.children)
        ks = [levels] * n if isinstance(levels, int) and not isinstance(levels, bool) else levels
        if (
            isinstance(ks, (str, bytes))
            or not isinstance(ks, Sequence)
            or len(ks) != n
            or not all(isinstance(k, int) and not isinstance(k, bool) and k >= 1 for k in ks)
        ):
            raise ValueError(
                f"module_level must be an int >= 1 or one such int per network ({n}), got {levels!r}"
            )
        return list(ks)

    def set_module_level(self, levels: int | Sequence[int]) -> bool:
        """TS ``setModuleLevel`` (fix round B2): per network, rounds of "expand every visible module below its
        level that can expand (``Module.can_expand``), in ``children`` order", each followed by ``calc_flow`` and
        the network's ``update_flow_threshold`` (no layout), until a round finds none; then one ``update_layout``
        if something was expanded. Never regroups. Returns whether some module was expanded."""
        ks = self._levels(levels)
        changed = False
        for network, k in zip(self.diagram.children, ks, strict=True):
            while True:
                round_modules = [
                    m for m in network.children if m.is_visible and m.module_level < k and m.can_expand
                ]
                if not round_modules:
                    break
                for module in round_modules:
                    module.expand()
                changed = True
                self.diagram.calc_flow()
                network.update_flow_threshold(self.options.flow_threshold)
        if changed:
            self.update_layout()
        return changed

    def apply_module_level(self, levels: int | Sequence[int]) -> list[dict[str, Any]]:
        """``module_level=k`` (v2-hierarchy.md §10.1, fix round B2): one ``set_module_level``. Returns the issued
        ops: ``[{"op": "setModuleLevel", "levels": [k per network]}]``, or ``[]`` if nothing was expanded."""
        ks = self._levels(levels)
        return [{"op": "setModuleLevel", "levels": ks}] if self.set_module_level(ks) else []

    def apply_module_names(self, items: Iterable[tuple[int, str, str]]) -> list[dict[str, Any]]:
        """``module_names=`` (v4-names-order.md §2): one TS ``setModuleName(module, name)`` per
        ``(network_index, module_id, name)``, in order, the module looked up with ``network.get_module`` at its turn.
        Returns the issued ops as ``{"op": "setModuleName", "networkIndex", "moduleId", "name"}`` records."""
        ops: list[dict[str, Any]] = []
        for network_index, module_id, name in items:
            network = self._network(network_index)
            module = network.get_module(module_id)
            if module is None:
                raise ValueError(
                    f"module_names: no module {module_id!r} in network {network.network_id!r}"
                    f"{_missing_module_hint(network, module_id)}"
                )
            self.set_module_name(module, name)
            ops.append(
                {"op": "setModuleName", "networkIndex": network_index, "moduleId": module_id, "name": name}
            )
        return ops

    def apply_module_order(self, order: Iterable[tuple[int, Sequence[str]]]) -> list[dict[str, Any]]:
        """``module_order=`` as at most one TS ``setModuleOrder`` op (v4-names-order.md §3, fix round B1).

        ``order`` holds ``(network_index, ids)`` pairs; ``ids`` lists visible module ids bottom to top, with at most
        one ``"..."`` standing for the unlisted visible modules in their current relative order (without one, they
        go above the listed ones). Per network the target visible order is built from ``network.children``. Networks
        whose target equals their current visible order are left alone (not frozen); the others get the full
        visible target in one ``set_module_order`` call (one layout without ``calc_flow``, bit-identical to the
        former sequence of adjacent ``moveModule("down")`` swaps). Returns the issued op, if any, as
        ``{"op": "setModuleOrder", "order": [[networkIndex, [moduleId, ...]], ...]}`` (networks ascending).
        """
        resolved: dict[int, tuple[Network, list[Module | None]]] = {}
        for network_index, ids in order:
            network = self._network(network_index)
            if network_index in resolved:
                raise ValueError(f"module_order: network {network.network_id!r} is given twice")
            if sum(1 for module_id in ids if module_id == "...") > 1:
                raise ValueError(
                    f"module_order: network {network.network_id!r} has more than one '...' (Ellipsis)"
                )
            modules: list[Module | None] = []
            seen: set[str] = set()
            for module_id in ids:
                if module_id == "...":
                    modules.append(None)
                    continue
                if module_id in seen:
                    raise ValueError(
                        f"module_order: module {module_id!r} is listed twice for network {network.network_id!r}"
                    )
                seen.add(module_id)
                module = network.get_module(module_id)
                if module is None:
                    raise ValueError(
                        f"module_order: no module {module_id!r} in network {network.network_id!r}"
                        f"{_missing_module_hint(network, module_id)}"
                    )
                if not module.is_visible:
                    raise ValueError(
                        f"module_order: module {module_id!r} in network {network.network_id!r} is not shown (its "
                        "flow is below the flow threshold, or zero); only visible modules can be placed"
                    )
                modules.append(module)
            resolved[network_index] = (network, modules)

        orders: list[tuple[Network, list[Module]]] = []
        recorded: list[list[Any]] = []
        for network_index in sorted(resolved):
            network, modules = resolved[network_index]
            listed = {id(m) for m in modules if m is not None}
            rest = [m for m in network.children if m.is_visible and id(m) not in listed]
            if None in modules:
                k = modules.index(None)
                target = [*modules[:k], *rest, *modules[k + 1 :]]
            else:
                target = [*modules, *rest]
            visible = [m for m in network.children if m.is_visible]
            if all(a is b for a, b in zip(target, visible, strict=True)):
                continue
            placed = [m for m in target if m is not None]
            orders.append((network, placed))
            recorded.append([network_index, [m.module_id for m in placed]])
        if not orders:
            return []
        self.set_module_order(orders)
        return [{"op": "setModuleOrder", "order": recorded}]

    def apply_expand_list(self, items: Iterable[tuple[int | str, str]]) -> None:
        """``expand=[(network, module_id), ...]`` (v2-hierarchy.md §10.3): ``network`` is an index or a network id;
        the module is looked up when its turn comes. A missing module or a refused expand raises ``ValueError``."""
        for network_ref, module_id in items:
            network = self._network(network_ref)
            module = network.get_module(str(module_id))
            if module is None:
                raise ValueError(
                    f"no module {module_id!r} in network {network.network_id!r}"
                    f"{_missing_module_hint(network, str(module_id))}"
                )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                ok = self.expand(module)
            if not ok:
                message = str(caught[-1].message) if caught else "refused"
                if message.startswith("Module can't be expanded"):
                    message = f"it has no sub-modules, or some of its nodes sit directly in it ({message})"
                raise ValueError(
                    f"cannot expand module {module_id!r} in network {network.network_id!r}: {message}"
                )

    def _network(self, ref: int | str) -> Network:
        networks = self.diagram.children
        if isinstance(ref, int) and not isinstance(ref, bool):
            if not 0 <= ref < len(networks):
                raise ValueError(f"no network {ref}")
            return networks[ref]
        network = self.diagram.get_network(ref)
        if network is None:
            raise ValueError(f"no network {ref!r}")
        return network

    def apply_highlight(
        self, label_of_leaf: Callable[[LeafNode], int | None], colors: Sequence[Any]
    ) -> list[int]:
        """``layout(highlight=...)`` (v2-highlight.md §7.1): write each leaf's label index ``k`` (or none) into
        ``metadata[HIGHLIGHT_KEY]`` as ``str(k)`` and run ``color_categorical_metadata`` with ``str(k) -> colors[k]``.

        Every leaf built from the files (``Network.built_leaf_nodes``) gets a metadata dict (a copy; other keys
        kept), as input-node metadata would. Returns the highlight index of each label.
        """
        for network in self.diagram.children:
            for leaf in network.built_leaf_nodes:
                k = label_of_leaf(leaf)
                md = dict(leaf.metadata) if isinstance(leaf.metadata, Mapping) else {}
                md.pop(HIGHLIGHT_KEY, None)
                if k is not None:
                    md[HIGHLIGHT_KEY] = str(k)
                leaf.metadata = md
        self.color_categorical_metadata(HIGHLIGHT_KEY, {str(k): c for k, c in enumerate(colors)})
        indices = [self.get_highlight_index(c) for c in colors]
        return indices

    def _module_at(self, operation: Mapping[str, Any]) -> Module:
        """``moduleId`` (looked up with ``network.get_module`` at op time), else ``moduleIndex`` (children order).

        ``moduleId`` wins when both are given, as in the TS harness's ``moduleAt``."""
        network = self.diagram.children[operation["networkIndex"]]
        module_id = operation.get("moduleId")
        if module_id is not None:
            module = network.get_module(module_id)
            if module is None:
                raise ValueError(f"no module {module_id!r} in network {operation['networkIndex']}")
            return module
        return network.children[operation["moduleIndex"]]

    def _leaf_at(self, ref: Mapping[str, Any]) -> LeafNode:
        network = self.diagram.children[ref["networkIndex"]]
        leaf = network.get_leaf_node(ref["identifier"])
        if leaf is None:
            raise ValueError(f"no leaf {ref['identifier']!r} in network {ref['networkIndex']}")
        return leaf

    def apply(self, operation: Mapping[str, Any]) -> bool | None:
        """Run one fixture/store operation record (``{"op": name, ...}``), except ``setNetworks`` and the macros.

        The refusable ops (``expand``, ``regroup``, ``moveModule``) return their success flag. A refusal raises
        ``RuntimeError``, unless the record carries the expected ``"result"`` (fuzz records), which must match.
        """
        op = operation["op"]
        result: bool | None = None
        if op == "colorMatchingModulesInAllNetworks":
            self.color_matching_modules_in_all_networks()
        elif op == "colorModuleIdsInAllNetworks":
            self.color_module_ids_in_all_networks()
        elif op == "colorNodesInModulesInAllNetworks":
            network_index = operation.get("networkIndex")
            self.color_nodes_in_modules_in_all_networks(
                None if network_index is None else self.diagram.children[network_index].network_id
            )
        elif op == "clearColors":
            self.clear_colors()
        elif op == "setOption":
            self.set_option(operation["key"], operation["value"])
        elif op == "resetLayout":
            self.reset_layout()
        elif op == "colorSelectedNodes":
            nodes = [self._leaf_at(ref) for ref in operation["nodes"]]
            self.color_selected_nodes(nodes, operation["color"])
        elif op == "colorByLayer":
            self.color_by_layer()
        elif op == "colorByPhysicalId":
            self.color_by_physical_id()
        elif op == "colorCategoricalMetadata":
            self.color_categorical_metadata(operation["name"], {k: c for k, c in operation["colors"]})
        elif op == "colorRealMetadata":
            self.color_real_metadata(operation["name"], operation["bins"])
        elif op == "colorRealIntervals":
            breaks, colors = operation["breaks"], operation["colors"]
            self.color_real_intervals(
                operation["name"],
                None,
                lambda v: _js_get(colors, sum(1 for b in breaks if b <= v)),
                operation["centers"],
            )
        elif op == "setDefaultHighlightColor":
            self.set_default_highlight_color(operation["color"])
        elif op == "setSelectedScheme":
            self.set_selected_scheme(operation["name"])
        elif op == "setSelectedTone":
            self.set_selected_tone(operation["tone"])
        elif op == "setSelectedOffset":
            self.set_selected_offset(operation["offset"])
        elif op == "colorModuleHierarchyInAllNetworks":
            self.color_module_hierarchy_in_all_networks()
        elif op == "setHighlightColors":
            self.set_highlight_colors(operation["colors"])
        elif op == "setNetworkName":
            self.set_network_name(
                self.diagram.children[operation["networkIndex"]].network_id, operation["name"]
            )
        elif op == "setModuleName":
            self.set_module_name(self._module_at(operation), operation["name"])
        elif op in (
            "colorModule",
            "expand",
            "regroup",
            "moveModule",
            "colorMatchingModules",
            "colorModuleIds",
            "colorNodesInModule",
        ):
            module = self._module_at(operation)
            if op == "colorModule":
                self.color_module(module, operation["color"])
            elif op == "expand":
                result = self.expand(module)
            elif op == "regroup":
                result = self.regroup(module)
            elif op == "moveModule":
                result = self.move_module(module, operation["direction"])
            elif op == "colorMatchingModules":
                self.color_matching_modules(module, operation["color"], operation.get("side"))
            elif op == "colorModuleIds":
                self.color_module_ids(module, operation["color"])
            else:
                self.color_nodes_in_module(module, operation["color"])
        elif op == "moduleLevel":
            self.apply_module_level(operation["levels"])
        elif op == "setModuleLevel":
            self.set_module_level(operation["levels"])
        elif op == "setModuleOrder":
            self.set_module_order(
                [
                    (
                        self.diagram.children[network_index],
                        [self._module_at({"networkIndex": network_index, "moduleId": i}) for i in ids],
                    )
                    for network_index, ids in operation["order"]
                ]
            )
        elif op == "moduleOrder":
            self.apply_module_order((ni, ids) for ni, ids in operation["order"])
        else:
            raise ValueError(f"unknown operation {op!r}")
        if op in REFUSABLE_OPS:
            expected = operation.get("result")
            if expected is None and not result:
                raise RuntimeError(f"{op} refused for {operation}")
            if expected is not None and expected is not result:
                raise RuntimeError(f"{op} returned {result}, expected {expected}")
        return result

    def replay(self, networks: Sequence[NetworkFile], operations: Sequence[Mapping[str, Any]]) -> None:
        """``set_networks(networks)`` followed by the operations after the leading ``{"op": "setNetworks"}``."""
        ops = list(operations)
        if ops and ops[0]["op"] == "setNetworks":
            ops = ops[1:]
        self.set_networks(networks)
        for operation in ops:
            self.apply(operation)


def _missing_module_hint(network: Network, module_id: str) -> str:
    """Why ``expand`` found no module ``module_id``: a sub-module whose parent is not expanded yet, or a module
    that is already expanded (only its sub-modules are shown)."""
    shown = list(network.modules_by_id)
    parent = next((m for m in shown if module_id.startswith(m + ":")), None)
    if parent is not None:
        k = module_id.count(":") + 1
        leaves = network.modules_by_id[parent].get_leaf_nodes()
        if any(
            leaf.level > k and leaf.tree_path.ancestor_at_level_as_string(k) == module_id for leaf in leaves
        ):
            return f"; expand its parent module {parent!r} first, e.g. expand=[(network, {parent!r}), ...]"
        return ""
    if any(m.startswith(module_id + ":") for m in shown):
        return " (it is already expanded: its sub-modules are shown)"
    return ""
