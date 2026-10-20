"""Port of ``alluvial/HighlightGroup.ts``: the leaves of a module sharing ``(highlight_index, insignificant)``."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from .alluvial_node import AlluvialNode
from .branch import Branch
from .depth import HIGHLIGHT_GROUP
from .side import LEFT, RIGHT

if TYPE_CHECKING:
    from .module import Module

NOT_HIGHLIGHTED = -1


class HighlightGroup(AlluvialNode):
    __slots__ = ("highlight_index", "insignificant")

    depth = HIGHLIGHT_GROUP

    def __init__(
        self, parent: Module, highlight_index: int = NOT_HIGHLIGHTED, insignificant: bool = False
    ) -> None:
        super().__init__(
            parent, parent.network_id, f"{parent.id}_group{'i' if insignificant else ''}{highlight_index}"
        )
        self.children = [Branch(self, LEFT), Branch(self, RIGHT)]
        parent.add_child(self)
        self.highlight_index = highlight_index
        self.insignificant = insignificant

    @property
    def is_highlighted(self) -> bool:
        return self.highlight_index != NOT_HIGHLIGHTED

    @property
    def left(self) -> Branch:
        return self.children[0]

    @property
    def right(self) -> Branch:
        return self.children[1]

    @property
    def is_empty(self) -> bool:
        return self.left.is_empty and self.right.is_empty

    @property
    def num_leaf_nodes(self) -> int:
        return self.left.num_leaf_nodes

    @property
    def child_flow(self) -> float:
        return self.left.child_flow

    def leaf_nodes(self) -> Iterator[Any]:
        yield from self.left.leaf_nodes()
