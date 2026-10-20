"""Port of ``alluvial/StreamlineNode.ts``: the leaves of a branch that share one opposite group.

The node's own ``id`` is ``""``; its key is ``current_id`` (``source--target`` when linked, ``source`` when
dangling). Children are index-tracked (each leaf stores its index per side) and removed by swap-remove.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from .alluvial_node import AlluvialNode
from .depth import HIGHLIGHT_GROUP, STREAMLINE_NODE
from .side import LEFT, opposite, side_to_string
from .streamline_link import StreamlineLink

if TYPE_CHECKING:
    from .branch import Branch
    from .leaf_node import LeafNode


class StreamlineNode(AlluvialNode):
    __slots__ = ("link", "side", "source_id", "target_id")

    depth = STREAMLINE_NODE

    def __init__(self, parent: Branch, id: str) -> None:
        super().__init__(parent, parent.network_id, "")
        self.link: StreamlineLink | None = None
        parent.add_child(self)
        self.side = parent.side
        parts = id.split("--")
        self.source_id = parts[0]
        self.target_id: str | None = parts[1] if len(parts) > 1 else None

    @property
    def num_leaf_nodes(self) -> int:
        return len(self.children)

    @property
    def current_id(self) -> str:
        return f"{self.source_id}--{self.target_id}" if not self.is_dangling else self.source_id

    @property
    def opposite_id(self) -> str:
        return f"{'NULL' if self.target_id is None else self.target_id}--{self.source_id}"

    @property
    def is_dangling(self) -> bool:
        return self.target_id is None

    @property
    def opposite_streamline_position(self) -> float:
        opp = self.opposite
        group = opp.get_ancestor(HIGHLIGHT_GROUP) if opp is not None else None
        if group is not None:
            module = group.parent
            if module is not None and module.is_visible:
                return -group.y
        return -math.inf

    @property
    def opposite(self) -> StreamlineNode | None:
        link = self.link
        if link is not None:
            return link.right if link.left is self else link.left
        return None

    @staticmethod
    def create_id(source: LeafNode, side: int, target: LeafNode | None = None) -> str:
        source_insignificant = "i" if source.insignificant else ""
        source_string = (
            f"{source.network_id}_module{source.module_id}"
            f"_group{source_insignificant}{source.highlight_index}_{side_to_string(side)}"
        )
        if target is None:
            return source_string
        target_insignificant = "i" if target.insignificant else ""
        target_string = (
            f"{target.network_id}_module{target.module_id}"
            f"_group{target_insignificant}{target.highlight_index}_{side_to_string(opposite(side))}"
        )
        return f"{source_string}--{target_string}"

    def add_child(self, node: Any) -> int:
        self.children.append(node)
        length = len(self.children)
        node.set_index(length - 1, self.side)
        return length

    def remove_child(self, node: Any) -> bool:
        children = self.children
        index = node.get_index(self.side)
        found = -1 < index < len(children)
        if found:
            children[index] = children[-1]
            children[index].set_index(index, self.side)
            node.set_index(-1, self.side)
            children.pop()
        return found

    def make_dangling(self) -> StreamlineNode:
        self.target_id = None
        return self

    def link_to(self, opposite_node: StreamlineNode) -> StreamlineNode:
        reverse = self.side == LEFT
        self.link = opposite_node.link = StreamlineLink(self, opposite_node, reverse)
        return self

    def remove_link(self) -> StreamlineNode:
        if self.link is not None:
            self.link.remove()
        return self
