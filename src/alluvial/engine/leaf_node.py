"""Port of ``alluvial/LeafNode.ts``: one input node, attached to a left and a right streamline node.

``add()`` and ``_remove()`` follow the TS step order exactly (own streamline node first, then detach the opposite
leaf, then create the opposite streamline node and link, then re-append the opposite leaf, then append self;
left side before right side). ``update() = remove(); add()`` is the only mutation path.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .._jscompat import js_is_integer
from .._warnings import user_stacklevel
from ..tree_path import TreePath
from .alluvial_node import AlluvialNode
from .depth import HIGHLIGHT_GROUP, LEAF_NODE
from .highlight_group import NOT_HIGHLIGHTED, HighlightGroup
from .module import Module
from .side import LEFT, RIGHT, opposite, side_to_string
from .streamline_node import StreamlineNode

if TYPE_CHECKING:
    from ..io.types import Node
    from .branch import Branch
    from .network import Network


def _int_if_integral(x: Any) -> Any:
    return int(x) if isinstance(x, float) and js_is_integer(x) else x


class LeafNode(AlluvialNode):
    __slots__ = (
        "highlight_index",
        "identifier",
        "layer_id",
        "left_index",
        "left_parent",
        "metadata",
        "module_level",
        "name",
        "network",
        "node_id",
        "opposite_nodes",
        "right_index",
        "right_parent",
        "state_id",
        "tree_path",
        "visible",
    )

    depth = LEAF_NODE

    def __init__(self, node: Node, network: Network) -> None:
        super().__init__(None, network.network_id, node.path)
        self.name = node.name
        self._flow = node.flow
        self.node_id = node.id
        self.state_id = node.state_id if node.state_id is not None else None
        self.layer_id = node.layer_id if node.layer_id is not None else None
        self.metadata = node.metadata if node.metadata is not None else None
        self.identifier = node.identifier
        self.tree_path = TreePath(node.path)
        hi = node.highlight_index
        self.highlight_index = (
            _int_if_integral(hi) if hi is not None and js_is_integer(hi) else NOT_HIGHLIGHTED
        )
        ml = node.module_level
        # only an integer level >= 1 is meaningful (TS LeafNode, fix round E18): 0, negatives, fractions -> 1
        self.module_level = _int_if_integral(ml) if js_is_integer(ml) and ml >= 1 else 1
        self.visible = True
        self.left_index = -1
        self.right_index = -1
        self.left_parent: StreamlineNode | None = None
        self.right_parent: StreamlineNode | None = None
        self.opposite_nodes: dict[int, LeafNode | None] = {LEFT: None, RIGHT: None}
        self.network = network

    @property
    def insignificant(self) -> bool:
        return not self.tree_path.is_significant(self.module_level - 1)

    @property
    def flow(self) -> float:
        return self._flow if self.visible else 0

    @flow.setter
    def flow(self, value: float) -> None:
        self._flow = value

    @property
    def level(self) -> int:
        return self.tree_path.level

    @property
    def module_id(self) -> str:
        return self.tree_path.ancestor_at_level_as_string(self.module_level)

    @property
    def child_flow(self) -> float:
        return self.flow

    def get_parent(self, side: int) -> StreamlineNode | None:
        return self.left_parent if side == LEFT else self.right_parent

    def set_parent(self, parent: StreamlineNode | None, side: int) -> None:
        if side == LEFT:
            self.left_parent = parent
        else:
            self.right_parent = parent

    def get_index(self, side: int) -> int:
        return self.left_index if side == LEFT else self.right_index

    def set_index(self, index: int, side: int) -> None:
        if side == LEFT:
            self.left_index = index
        else:
            self.right_index = index

    def get_opposite(self, side: int) -> LeafNode | None:
        return self.opposite_nodes[side]

    def set_opposite(self, node: LeafNode | None, side: int) -> None:
        self.opposite_nodes[side] = node

    def add(self) -> None:
        network = self.network
        module = network.get_module(self.module_id)
        if module is None:
            module = Module(network, self.module_id, self.module_level)

        group = module.get_group(self.highlight_index, self.insignificant)
        if group is None:
            group = HighlightGroup(module, self.highlight_index, self.insignificant)

        for branch in group.children:
            side = branch.side
            opposite_node = self.get_opposite(side)
            neighbor_network = network.get_neighbor(side)

            if opposite_node is None:
                # Only mutually registered leaves are linked (E6): with duplicate identifiers only the registered
                # (last) duplicate links; the others stay dangling instead of stealing the opposite leaf.
                candidate = (
                    neighbor_network.get_leaf_node(self.identifier) if neighbor_network is not None else None
                )
                opposite_node = (
                    candidate
                    if candidate is not None and network.get_leaf_node(self.identifier) is self
                    else None
                )
                self.set_opposite(opposite_node, side)

            streamline_id = StreamlineNode.create_id(self, side, opposite_node)
            streamline_node = network.get_streamline_node(streamline_id)

            if streamline_node is None:
                streamline_node = StreamlineNode(branch, streamline_id)
                network.set_streamline_node(streamline_node.current_id, streamline_node)

            if opposite_node is not None:
                opposite_side = opposite(side)
                opposite_branch = opposite_node._remove_from_side(opposite_side)

                opposite_id = streamline_node.opposite_id
                opposite_streamline_node = neighbor_network.get_streamline_node(opposite_id)

                if opposite_streamline_node is None:
                    opposite_streamline_node = StreamlineNode(opposite_branch, opposite_id)
                    neighbor_network.set_streamline_node(
                        opposite_streamline_node.current_id, opposite_streamline_node
                    )
                    streamline_node.link_to(opposite_streamline_node)

                opposite_streamline_node.add_child(opposite_node)
                opposite_node.set_parent(opposite_streamline_node, opposite_side)

            streamline_node.add_child(self)
            self.set_parent(streamline_node, side)

    def update(self) -> None:
        self._remove()
        self.add()

    def leaf_nodes(self) -> Iterator[LeafNode]:
        yield self

    def _remove(self) -> None:
        group = self.left_parent.get_ancestor(HIGHLIGHT_GROUP) if self.left_parent is not None else None

        self._remove_from_side(LEFT)
        self._remove_from_side(RIGHT)

        module = group.parent if group is not None else None
        network = module.parent if module is not None else None

        if group is not None and group.is_empty:
            module.remove_child(group)

        # Keep an emptied module when the leaf goes straight back into it (colour changes, E4): re-creating it
        # would lose its name, position and flow.
        if module is not None and module.is_empty and module.module_id != self.module_id:
            network.remove_child(module)

    def _remove_from_side(self, side: int) -> Branch | None:
        streamline_node = self.get_parent(side)

        if streamline_node is None:
            warnings.warn(
                f"Node {self.id} has no {side_to_string(side)} parent",
                RuntimeWarning,
                stacklevel=user_stacklevel(),
            )
            return None

        branch = streamline_node.parent

        streamline_node.remove_child(self)
        self.set_parent(None, side)

        if streamline_node.is_empty:
            opposite_streamline_node = streamline_node.opposite

            if opposite_streamline_node is not None:
                neighbor_network = self.network.get_neighbor(side)

                neighbor_network.remove_streamline_node(opposite_streamline_node.current_id)
                opposite_streamline_node.make_dangling().remove_link()

                already_dangling = neighbor_network.get_streamline_node(opposite_streamline_node.current_id)

                if already_dangling is not None:
                    opposite_side = opposite(side)
                    for node in list(opposite_streamline_node.children):
                        already_dangling.add_child(node)
                        node.set_parent(already_dangling, opposite_side)

                    opposite_streamline_node.children.clear()
                    if opposite_streamline_node.parent is not None:
                        opposite_streamline_node.parent.remove_child(opposite_streamline_node)
                else:
                    neighbor_network.set_streamline_node(
                        opposite_streamline_node.current_id, opposite_streamline_node
                    )

            self.network.remove_streamline_node(streamline_node.current_id)
            branch.remove_child(streamline_node)

        return branch
