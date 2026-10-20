"""Port of ``alluvial/Branch.ts``: the left or right half of a highlight group."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .alluvial_node import AlluvialNode
from .depth import BRANCH
from .side import LEFT, side_to_string

if TYPE_CHECKING:
    from .highlight_group import HighlightGroup


class Branch(AlluvialNode):
    __slots__ = ("side",)

    depth = BRANCH

    def __init__(self, parent: HighlightGroup, side: int) -> None:
        super().__init__(parent, parent.network_id, side_to_string(side))
        self.side = side

    @property
    def is_left(self) -> bool:
        return self.side == LEFT
