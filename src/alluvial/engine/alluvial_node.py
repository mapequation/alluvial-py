"""Port of ``alluvial/AlluvialNode.ts`` (``Layout`` and the ``AlluvialNode`` base class).

``flow`` is a cached field written only by ``Diagram.calc_flow`` (LeafNode overrides it). ``remove_child`` is a
swap-remove and every children search is by identity.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from .._jscompat import index_of_identity


class Layout:
    """Port of TS ``Layout``: ``x, y, width, height`` (all 0 initially)."""

    __slots__ = ("height", "width", "x", "y")

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.width = 0.0
        self.height = 0.0

    def set_layout(self, x: float, y: float, width: float, height: float) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class AlluvialNode(Layout):
    """Port of TS ``AlluvialNode``."""

    __slots__ = ("_flow", "children", "id", "network_id", "parent")

    depth: int = -1

    def __init__(self, parent: Any, network_id: str, id: str = "") -> None:
        super().__init__()
        self._flow = 0.0
        self.children: list[Any] = []
        self.parent = parent
        self.network_id = network_id
        self.id = id

    @property
    def flow(self) -> float:
        return self._flow

    @flow.setter
    def flow(self, value: float) -> None:
        self._flow = value

    @property
    def is_first_child(self) -> bool:
        if self.parent is None:
            return False
        return index_of_identity(self.parent.children, self) == 0

    @property
    def is_last_child(self) -> bool:
        num_children = len(self.parent.children) if self.parent is not None else -1
        if self.parent is None:
            return False
        return index_of_identity(self.parent.children, self) == num_children - 1

    @property
    def is_empty(self) -> bool:
        return len(self.children) == 0

    @property
    def num_leaf_nodes(self) -> int:
        num = 0
        for child in self.children:
            num = num + child.num_leaf_nodes
        return num

    @property
    def child_flow(self) -> float:
        total = 0.0
        for child in self.children:
            total = total + child.flow
        return total

    def get_ancestor(self, depth: int) -> Any:
        if self.depth == depth:
            return self
        if self.parent is None or self.depth < depth:
            return None
        return self.parent.get_ancestor(depth)

    def add_child(self, node: Any) -> int:
        self.children.append(node)
        return len(self.children)

    def remove_child(self, node: Any) -> bool:
        children = self.children
        index = index_of_identity(children, node)
        found = index > -1
        if found:
            children[index] = children[-1]
            children.pop()
        return found

    def get_leaf_nodes(self) -> list[Any]:
        return list(self.leaf_nodes())

    def leaf_nodes(self) -> Iterator[Any]:
        for child in self.children:
            yield from child.leaf_nodes()

    def __iter__(self) -> Iterator[Any]:
        return iter(self.children)

    def for_each_depth_first_pre_order_while(
        self, predicate: Callable[[Any], bool], callback: Callable[[Any, int, list[Any]], None]
    ) -> None:
        children = [c for c in self.children if predicate(c)]
        for i, child in enumerate(children):
            callback(child, i, children)
            child.for_each_depth_first_pre_order_while(predicate, callback)

    def for_each_depth_first_post_order_while(
        self, predicate: Callable[[Any], bool], callback: Callable[[Any, int, list[Any]], None]
    ) -> None:
        children = [c for c in self.children if predicate(c)]
        for i, child in enumerate(children):
            child.for_each_depth_first_post_order_while(predicate, callback)
            callback(child, i, children)
