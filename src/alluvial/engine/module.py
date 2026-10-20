"""Port of ``alluvial/Module.ts``: a module of one network, holding highlight groups.

``flow`` is cached (``calc_flow``); ``is_visible`` and ``highlight_index`` read the cached flows. ``expand``,
``regroup`` and ``move`` follow docs/dev/port-notes/v2-hierarchy.md §3-§5 (refusals warn with the TS text and
return False).
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from .._jscompat import index_of_identity, js_max
from .._warnings import user_stacklevel
from ..tree_path import TreePath
from ._utils import PriorityQueue, js_div
from .alluvial_node import AlluvialNode
from .depth import MODULE
from .highlight_group import NOT_HIGHLIGHTED
from .side import LEFT

if TYPE_CHECKING:
    from .highlight_group import HighlightGroup
    from .network import Network
    from .streamline_link import StreamlineLink


class SimilarModule(SimpleNamespace):
    module: Module
    similarity: float


class Module(AlluvialNode):
    __slots__ = (
        "enter_flow",
        "exit_flow",
        "index",
        "links",
        "margin",
        "module_id",
        "module_level",
        "name",
        "path",
    )

    depth = MODULE

    def __init__(self, parent: Network, module_id: str, module_level: int = 1) -> None:
        super().__init__(parent, parent.network_id, f"{parent.network_id}_module{module_id}")
        self.margin = 0.0
        self.name = ""
        self.enter_flow = 0.0
        self.exit_flow = 0.0
        self.links: dict[str, float] | None = None
        self.module_level = module_level
        self.module_id = module_id
        self.path = TreePath.to_array(module_id)
        self.index = parent.add_child(self) - 1

        infomap_module = parent.infomap_modules_by_path.get(module_id)
        if infomap_module is not None:
            self.enter_flow = infomap_module.enter_flow
            self.exit_flow = infomap_module.exit_flow

        links = parent.module_links.get(module_id)
        if links is not None:
            self.links = {target: flow for target, flow in links}

    def get_largest_leaf_nodes(self, num_values: int = 5, aggregate: bool = False) -> list[Any]:
        """Top ``num_values`` leaves by flow; with ``aggregate`` the flows are summed per physical node id.

        Aggregated entries are copies (``SimpleNamespace``) of the first leaf of each node id with the summed flow.
        """
        if not aggregate:
            nodes: Iterator[Any] = self.leaf_nodes()
        else:
            physical: dict[Any, SimpleNamespace] = {}
            for node in self.leaf_nodes():
                if node.node_id not in physical:
                    physical[node.node_id] = SimpleNamespace(
                        name=node.name,
                        node_id=node.node_id,
                        state_id=node.state_id,
                        layer_id=node.layer_id,
                        identifier=node.identifier,
                        highlight_index=node.highlight_index,
                        module_level=node.module_level,
                        flow=0,
                    )
                entry = physical[node.node_id]
                entry.flow = entry.flow + node.flow
            nodes = iter(physical.values())
        return PriorityQueue(num_values, lambda n: n.flow, nodes).to_list()

    @property
    def x1(self) -> float:
        return self.x

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def name_position(self) -> tuple[float, float]:
        x1, x2, y, height = self.x1, self.x2, self.y, self.height
        padding = 5
        width = 15
        text_offset = width + padding
        if self.parent.is_first_child:
            x = x1 - text_offset
        elif self.parent.is_last_child:
            x = x2 + text_offset
        else:
            x = (x1 + x2) / 2
        return x, y + height / 2

    @property
    def text_anchor(self) -> str | None:
        if self.parent.is_first_child:
            return "end"
        if self.parent.is_last_child:
            return "start"
        return None

    @property
    def id_position(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2, self.y + self.height / 2

    @property
    def network_name(self) -> str:
        name = self.parent.name if self.parent is not None else None
        return "" if name is None else name

    @property
    def is_visible(self) -> bool:
        return self.flow >= self._flow_threshold and self.flow > 0

    @property
    def has_submodules(self) -> bool:
        return self.module_level < self.max_module_level

    @property
    def is_top_module(self) -> bool:
        return self.module_level == 1

    @property
    def is_leaf_module(self) -> bool:
        return not self.has_submodules

    @property
    def is_highlighted(self) -> bool:
        return any(group.is_highlighted for group in self.children)

    @property
    def highlight_index(self) -> int:
        return self._largest_group_highlight_index()

    @property
    def largest_node_id(self) -> float:
        max_id: float = -1
        for node in self.leaf_nodes():
            max_id = js_max(max_id, node.node_id)
        return max_id

    @property
    def mean_node_id(self) -> float:
        mean_id = 0
        n = 0
        for node in self.leaf_nodes():
            n += 1
            mean_id = mean_id + node.node_id
        if n == 0:
            return -1
        return mean_id / n

    @property
    def max_module_level(self) -> int:
        max_module_level = self.module_level
        for node in self.leaf_nodes():
            max_module_level = max(max_module_level, node.level - 1)
        return max_module_level

    @property
    def _flow_threshold(self) -> float:
        return self.parent.flow_threshold if self.parent is not None else 0

    def _largest_group_highlight_index(self) -> int:
        max_flow = float("-inf")
        highlight_index = NOT_HIGHLIGHTED
        for group in self.children:
            if group.flow > max_flow:
                max_flow = group.flow
                highlight_index = group.highlight_index
        return highlight_index

    def get_group(self, highlight_index: int, insignificant: bool) -> HighlightGroup | None:
        for group in self.children:
            if group.highlight_index == highlight_index and group.insignificant == insignificant:
                return group
        return None

    @property
    def parent_index(self) -> int:
        """TS ``parentIndex``: identity index in ``network.children`` (-1 for a removed module)."""
        return index_of_identity(self.parent.children, self) if self.parent is not None else 0

    def _siblings(self) -> list[Module]:
        """TS private ``siblings``: the modules sharing the parent path, by ``isAncestor`` (path prefix up to a ``:``)."""
        if self.parent is None:
            return []
        modules = self.parent.children
        module_level = self.module_level - 1
        if module_level < 1:
            return modules
        parent_path = TreePath.ancestor_at_level(self.module_id, module_level)
        return [module for module in modules if parent_path.is_ancestor(module.module_id)]

    @property
    def can_expand(self) -> bool:
        """TS ``canExpand`` (fix round H4): ``expand()`` succeeds, i.e. the module has leaf nodes and all of them
        lie deeper than the next module level. ``is_leaf_module`` looks at the deepest leaf only."""
        leaf_nodes = self.get_leaf_nodes()
        new_module_level = self.module_level + 1
        return bool(leaf_nodes) and not any(node.level <= new_module_level for node in leaf_nodes)

    def expand(self) -> bool:
        new_module_level = self.module_level + 1

        if not self.can_expand:
            if not self.get_leaf_nodes():
                warnings.warn("No leaf nodes found", stacklevel=user_stacklevel())
            else:
                warnings.warn(
                    f"Module can't be expanded to level {new_module_level} "
                    f"because some nodes are at level {new_module_level - 1}",
                    stacklevel=user_stacklevel(),
                )
            return False

        leaf_nodes = self.get_leaf_nodes()

        network = self.parent
        if network is None:
            raise RuntimeError("No parent network found")

        network.is_custom_sorted = False

        for node in leaf_nodes:
            node.module_level = new_module_level
            node.update()

        return True

    def regroup(self) -> bool:
        if self.module_level <= 1:
            warnings.warn(
                f"Module with id {self.module_id} is already at module level {self.module_level}",
                stacklevel=user_stacklevel(),
            )
            return False

        leaf_nodes = [node for module in self._siblings() for node in module.get_leaf_nodes()]

        if not leaf_nodes:
            warnings.warn("No leaf nodes found", stacklevel=user_stacklevel())
            return False

        network = self.parent
        if network is None:
            raise RuntimeError("No parent network found")

        network.is_custom_sorted = False

        new_module_level = self.module_level - 1

        for node in leaf_nodes:
            node.module_level = new_module_level
            node.update()

        return True

    def move(self, direction: str) -> bool:
        """Swap with the neighbour in ``network.children`` (``"up"`` = higher index); sets ``is_custom_sorted``."""
        index = self.parent_index

        network = self.parent
        if network is None:
            raise RuntimeError("No parent network found")

        # fix round H1: the top boundary is the top visible module (children are visible + hidden after a
        # layout), so a move up never swaps with a hidden module.
        at_boundary = index >= len(network.visible_children) - 1 if direction == "up" else index == 0

        if at_boundary:
            warnings.warn(
                f"Can't move module {direction} because it is already at the "
                f"{'bottom' if direction == 'down' else 'top'}",
                stacklevel=user_stacklevel(),
            )
            return False

        index_direction = -1 if direction == "down" else 1
        new_index = index + index_direction

        network.is_custom_sorted = True
        network.move_to_index(index, new_index)
        return True

    def set_color(self, highlight_index: int) -> None:
        for node in self.get_leaf_nodes():
            if node.highlight_index == highlight_index:
                continue
            node.highlight_index = highlight_index
            node.update()

    def remove_colors(self) -> None:
        self.set_color(NOT_HIGHLIGHTED)

    def get_similar_modules(
        self, side: int, num_modules: int = 5, threshold: float = 1e-6
    ) -> list[SimilarModule]:
        modules: PriorityQueue[SimilarModule] = PriorityQueue(num_modules, lambda item: item.similarity)

        this_nodes, this_ids = _node_distribution(self)

        for module in self._connected_modules(side):
            if not module.is_visible:
                continue

            other_nodes, other_ids = _node_distribution(module)
            ids = list(dict.fromkeys(this_ids + other_ids))
            p = [this_nodes.get(i, 0) for i in ids]
            q = [other_nodes.get(i, 0) for i in ids]

            similarity = 1 - js_div(p, q, True)

            if similarity > threshold:
                modules.push(SimilarModule(module=module, similarity=similarity))

        return modules.to_list()

    def right_streamlines(self) -> Iterator[StreamlineLink]:
        for group in self.children:
            for streamline_node in group.right.children:
                opp = streamline_node.opposite
                module = opp.get_ancestor(MODULE) if opp is not None else None
                if module is None or not module.is_visible:
                    continue
                if streamline_node.link is not None:
                    yield streamline_node.link

    def _connected_modules(self, side: int) -> Iterator[Module]:
        module_ids: set[str] = set()
        for group in self.children:
            branch = group.left if side == LEFT else group.right
            for streamline_node in branch.children:
                opp = streamline_node.opposite
                module = opp.get_ancestor(MODULE) if opp is not None else None
                if module is not None and module.module_id not in module_ids:
                    module_ids.add(module.module_id)
                    yield module


def _node_distribution(module: Module) -> tuple[dict[str, float], list[str]]:
    nodes: dict[str, float] = {}
    for node in module.leaf_nodes():
        nodes[node.identifier] = node.flow
    return nodes, list(nodes)  # TS Map: insertion order (S5)
