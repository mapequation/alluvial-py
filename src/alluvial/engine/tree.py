"""Port of ``utils/Tree.ts``: the path-indexed tree used to order modules (stable, descending by summed key)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Generic, TypeVar

from ._utils import sort_by_number

T = TypeVar("T")


class _TreeNode:
    __slots__ = ("index", "nodes", "path", "size")

    def __init__(self, path: Any = 0) -> None:
        self.path = path
        self.size: float = 0
        self.nodes: list[Any] = []
        # child _TreeNodes by path segment: the TS `nodes.find(n => isTreeNode(n) && n.path === segment)` in O(1).
        # A key has at most one node (a second is only created when the find fails), and `===` agrees with dict
        # lookup for the segments used here (numbers, where 0 === -0 and 1 === 1.0, and strings), except NaN.
        self.index: dict[Any, _TreeNode] = {}


def _child(parent: _TreeNode, segment: Any) -> _TreeNode:
    """The child of ``parent`` with path ``segment``, created (appended) if missing."""
    if (
        segment != segment
    ):  # NaN: `NaN === NaN` is false, so TS never finds one; a dict could match it by identity
        node = _TreeNode(segment)
        parent.nodes.append(node)
        return node
    node = parent.index.get(segment)
    if node is None:
        node = _TreeNode(segment)
        parent.nodes.append(node)
        parent.index[segment] = node
    return node


class Tree(Generic[T]):
    """Items with a ``path`` sequence, grouped by path prefix; ``size`` of an inner node sums ``get_size``."""

    def __init__(self, children: Sequence[T], get_size: Callable[[T], float]) -> None:
        self.root = _TreeNode()
        for child in children:
            parent = self.root
            for segment in child.path:  # type: ignore[attr-defined]
                node = _child(parent, segment)
                node.size = node.size + get_size(child)
                parent = node
            parent.nodes.append(child)

    def sort(self, tree: _TreeNode | None = None) -> Tree[T]:
        tree = self.root if tree is None else tree
        sort_by_number(tree.nodes, lambda n: n.size if isinstance(n, _TreeNode) else 0, descending=True)
        for node in tree.nodes:
            if isinstance(node, _TreeNode):
                self.sort(node)
        return self

    def flatten(self, tree: _TreeNode | None = None) -> list[T]:
        tree = self.root if tree is None else tree
        flattened: list[T] = []
        for node in tree.nodes:
            if isinstance(node, _TreeNode):
                flattened.extend(self.flatten(node))
            else:
                flattened.append(node)
        return flattened
