"""Port of ``alluvial/Network.ts``: one partitioned network (a column of modules).

Keeps the TS registries (``nodes_by_identifier``, ``modules_by_id``, ``streamline_nodes_by_id``) with JS ``Map``
semantics. ``tree``/``hierarchical_children`` port the v2 super-module outlines (in v1 they list the visible
modules). ``metadata`` is not ported.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from .._jscompat import js_array_join, js_max, js_min
from ..io.identifiers import validate_network_nodes
from ..tree_path import TreePath
from ._utils import move_item, sort_by_number
from .alluvial_node import AlluvialNode, Layout
from .depth import NETWORK
from .leaf_node import LeafNode
from .module import Module

if TYPE_CHECKING:
    from ..io.types import InfomapModule, NetworkFile, Node
    from .diagram import Diagram
    from .streamline_link import StreamlineLink
    from .streamline_node import StreamlineNode

NOT_BIPARTITE = -1


class Network(AlluvialNode):
    __slots__ = (
        "bipartite_start_id",
        "built_leaf_nodes",
        "codelength",
        "directed",
        "flow_threshold",
        "infomap_modules_by_path",
        "is_custom_sorted",
        "layer_id",
        "module_links",
        "modules_by_id",
        "name",
        "nodes_by_identifier",
        "original_id",
        "streamline_nodes_by_id",
    )

    depth = NETWORK

    def __init__(self, parent: Diagram, file: NetworkFile) -> None:
        super().__init__(parent, file.id, file.id)
        self.is_custom_sorted = False
        self.flow_threshold: float = 0
        self.bipartite_start_id: int | None = NOT_BIPARTITE
        self.nodes_by_identifier: dict[Any, LeafNode] = {}
        # Every leaf built from the file, in node order (Python-only bookkeeping): the writers' input-order list,
        # also walked by `apply_highlight` (duplicate identifiers included, like input-node metadata would be).
        self.built_leaf_nodes: list[LeafNode] = []
        self.modules_by_id: dict[str, Module] = {}
        self.streamline_nodes_by_id: dict[str, StreamlineNode] = {}
        self.infomap_modules_by_path: dict[str, InfomapModule] = {}
        self.module_links: dict[str, list[tuple[str, float]]] = {}
        parent.add_child(self)
        self.name = file.name
        self.codelength = file.codelength if file.codelength is not None else 0
        self.layer_id = file.layer_id
        self.directed = file.directed if file.directed is not None else False
        self.original_id = file.original_id

        bipartite_start_id = getattr(file, "bipartite_start_id", None)
        if bipartite_start_id is not None:
            self.bipartite_start_id = bipartite_start_id

        if file.modules:
            self.infomap_modules_by_path = {js_array_join(m.path, ":"): m for m in file.modules}
            self.module_links = _create_link_map(file.modules, self.directed)

    def _first_leaf(self) -> LeafNode | None:
        return next(self.leaf_nodes(), None)

    @property
    def is_multilayer(self) -> bool:
        first = self._first_leaf()
        return first is not None and first.layer_id is not None

    @property
    def is_higher_order(self) -> bool:
        first = self._first_leaf()
        return self.is_multilayer or (first is not None and first.state_id is not None)

    @property
    def is_bipartite(self) -> bool:
        return self.bipartite_start_id != NOT_BIPARTITE

    def toggle_show_bipartite_nodes(self, show: bool) -> None:
        if not self.is_bipartite:
            return
        for node in self.leaf_nodes():
            node.visible = show if node.node_id >= self.bipartite_start_id else True

    @property
    def have_metadata(self) -> bool:
        """Some leaf has metadata (E12: not only the first one)."""
        return any(node.metadata is not None for node in self.leaf_nodes())

    @property
    def name_position(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.height + 15 + 5

    @property
    def visible_children(self) -> list[Module]:
        return [m for m in self.children if m.is_visible]

    @property
    def hierarchical_children(self) -> list[HierarchicalModule]:
        return list(self.tree.visit_breadth_first())

    @property
    def tree(self) -> TreeNode:
        root = TreeNode()
        for module in self.children:
            if not module.is_visible:
                continue
            parent: TreeNode = root
            path = TreePath(module.path)
            for module_level in range(1, module.module_level + 1):
                parent_path = path.ancestor_at_level_as_string(module_level)
                if not parent.has(parent_path):
                    is_leaf = module_level == module.module_level
                    parent = parent.create_child(parent_path, module_level, is_leaf)
                else:
                    parent = parent.get(parent_path)
                    # fix round E15a: a visible P was added as a leaf node before its visible sub-module P:x; make P
                    # a non-leaf node so that, in either order, its outline encloses P and its sub-modules.
                    if parent.is_leaf and module_level < module.module_level:
                        parent.make_non_leaf()
            parent.add_child(module)
        return root

    def update_flow_threshold(self, hidden_flow_fraction: float) -> None:
        max_hidden_flow = hidden_flow_fraction * self.flow
        flows = [module.flow for module in self.children]
        sort_by_number(flows, lambda flow: flow)

        hidden_flow = 0.0
        self.flow_threshold = math.inf

        for flow in flows:
            hidden_flow = hidden_flow + flow
            if hidden_flow > max_hidden_flow:
                self.flow_threshold = flow
                break

    @staticmethod
    def create(parent: Diagram, file: NetworkFile) -> Network:
        validate_network_nodes(file.nodes, file.name or "")  # TS Network.create (fix round E9)
        return Network(parent, file)

    def add_nodes(self, nodes: Sequence[Node]) -> None:
        self.nodes_by_identifier = {}
        leaf_nodes = []
        for node in nodes:
            leaf_node = LeafNode(node, self)
            self.nodes_by_identifier[leaf_node.identifier] = leaf_node
            leaf_nodes.append(leaf_node)
        self.built_leaf_nodes = leaf_nodes
        for leaf_node in leaf_nodes:
            leaf_node.add()

    def add_child(self, module: Module) -> int:
        length = super().add_child(module)
        self.modules_by_id[module.module_id] = module
        return length

    def remove_child(self, module: Module) -> bool:
        found = super().remove_child(module)
        self.modules_by_id.pop(module.module_id, None)
        return found

    def get_module(self, module_id: str) -> Module | None:
        return self.modules_by_id.get(module_id)

    def get_neighbor(self, side: int) -> Network | None:
        root = self.parent
        if root is not None:
            network_index = next(
                (i for i, network in enumerate(root.children) if network.network_id == self.network_id), -1
            )
            neighbor_network_index = network_index + side
            if (
                network_index > -1
                and neighbor_network_index > -1
                and neighbor_network_index < len(root.children)
            ):
                return root.children[neighbor_network_index]
        return None

    def get_leaf_node(self, identifier: Any) -> LeafNode | None:
        return self.nodes_by_identifier.get(identifier)

    def get_streamline_node(self, id: str) -> StreamlineNode | None:
        return self.streamline_nodes_by_id.get(id)

    def set_streamline_node(self, id: str, node: StreamlineNode) -> None:
        self.streamline_nodes_by_id[id] = node

    def remove_streamline_node(self, id: str) -> None:
        self.streamline_nodes_by_id.pop(id, None)

    def move_to_index(self, from_index: int, to_index: int) -> None:
        move_item(self.children, from_index, to_index)

    def set_module_order(self, modules: Sequence[Module]) -> bool:
        """TS ``Network.setModuleOrder`` (fix round B1): ``children`` becomes the listed modules (bottom to top)
        followed by the unlisted ones in their current order. Modules that are not children of this network, and
        repeats, are skipped; hidden modules may be listed (the next layout re-partitions ``children`` into
        visible + hidden, keeping each part's order). Always sets ``is_custom_sorted``; returns whether ``children``
        changed. The caller lays out."""
        listed: dict[int, Module] = {}
        for module in modules:
            if module.parent is self and self.get_module(module.module_id) is module:
                listed.setdefault(id(module), module)
        children = [*listed.values(), *(m for m in self.children if id(m) not in listed)]
        changed = any(a is not b for a, b in zip(children, self.children, strict=True))
        self.children = children
        self.is_custom_sorted = True
        return changed

    def get_links(self, streamline_threshold: float = 0) -> list[StreamlineLink]:
        links = [link for link in self._right_streamlines() if link.avg_height > streamline_threshold]
        links.sort(key=lambda link: (link.highlight_index, -link.avg_height))
        return links

    def _right_streamlines(self) -> Iterator[StreamlineLink]:
        for module in self.children:
            if not module.is_visible:
                continue
            yield from module.right_streamlines()


class TreeNode(Layout):
    """Port of the TS ``TreeNode`` in ``Network.ts``: a super-module box (v2 outlines)."""

    __slots__ = (
        "_max_height",
        "_max_y",
        "child_path_map",
        "children",
        "is_leaf",
        "max_module_level",
        "module_level",
        "parent",
        "path",
    )

    def __init__(
        self, path: str = "root", module_level: int = 1, is_leaf: bool = False, parent: TreeNode | None = None
    ) -> None:
        super().__init__()
        self.children: list[HierarchicalModule] = []
        self.child_path_map: dict[str, TreeNode] = {}
        self.max_module_level = 1
        self.y = math.inf
        self._max_y = -math.inf
        self._max_height = -math.inf
        self.path = path
        self.module_level = module_level
        self.is_leaf = is_leaf
        self.parent = parent
        if parent is not None:
            parent.children.append(self)
            parent.child_path_map[path] = self
            self._update_max_module_level(module_level)

    def has(self, path: str) -> bool:
        return path in self.child_path_map

    def get(self, path: str) -> TreeNode | None:
        return self.child_path_map.get(path)

    def create_child(self, path: str, module_level: int, is_leaf: bool) -> TreeNode:
        return TreeNode(path, module_level, is_leaf, self)

    def visit_breadth_first(self) -> Iterator[HierarchicalModule]:
        queue = self.children
        while queue:
            node = queue.pop(0)
            if isinstance(node, TreeNode):
                if not node.is_leaf:
                    yield node
                queue.extend(node.children)
            else:
                yield node

    def add_child(self, module: Module) -> None:
        if self.parent is None:
            raise RuntimeError("Module added to the root TreeNode")
        # A module whose own path already has visible sub-modules (a visible P with a visible P:x, fix round E15a)
        # joins that non-leaf node, so its outline encloses P and its sub-modules.
        (self.parent if self.is_leaf else self)._update_layout(module)
        self.children.append(module)

    def make_non_leaf(self) -> None:
        self.is_leaf = False
        for child in self.children:
            if not isinstance(child, TreeNode):
                self._update_layout(child)

    def _update_max_module_level(self, module_level: int) -> None:
        self.max_module_level = max(self.max_module_level, module_level)
        if self.parent is not None:
            self.parent._update_max_module_level(module_level)

    def _update_layout(self, module: Module) -> None:
        self.x = module.x
        self.width = module.width
        self.y = js_min(self.y, module.y)
        if module.y > self._max_y:
            self._max_y = module.y
            self._max_height = module.height
            self.height = js_max(self.height, abs(self.y - module.y) + module.height)
        else:
            self.height = js_max(self.height, abs(self.y - self._max_y) + self._max_height)
        if self.parent is not None:
            self.parent._update_layout(module)


HierarchicalModule = TreeNode | Module


def _create_link_map(
    modules: Sequence[InfomapModule], directed: bool = False
) -> dict[str, list[tuple[str, float]]]:
    link_map: dict[str, list[tuple[str, float]]] = {}

    def add_directed_link(source: str, target: str, flow: float) -> None:
        link_map.setdefault(source, []).append((target, flow))

    def add_link(source: str, target: str, flow: float) -> None:
        add_directed_link(source, target, flow)
        if not directed:
            add_directed_link(target, source, flow)

    for module in modules:
        module_id = js_array_join(module.path, ":")
        parent = "" if module.path[0] == 0 else module_id + ":"
        for link in module.links or ():
            add_link(parent + js_array_join([link.source]), parent + js_array_join([link.target]), link.flow)

    return link_map
