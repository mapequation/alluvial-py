"""Port of ``alluvial/StreamlineLink.ts``: the link between two streamline nodes of adjacent networks.

``left`` is always the streamline node in the left network (a right-branch node) and ``right`` the one in the
right network.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._jscompat import js_max, js_number_to_string

if TYPE_CHECKING:
    from .streamline_node import StreamlineNode


class StreamlineLink:
    __slots__ = ("left", "right")

    def __init__(self, left: StreamlineNode, right: StreamlineNode, reverse: bool = False) -> None:
        self.left = right if reverse else left
        self.right = left if reverse else right

    @property
    def id(self) -> str:
        return self.left.current_id if self.left is not None else ""

    @property
    def left_highlight_index(self) -> int:
        return self.left.parent.parent.highlight_index

    @property
    def right_highlight_index(self) -> int:
        return self.right.parent.parent.highlight_index

    @property
    def left_insignificant(self) -> bool:
        return self.left.parent.parent.insignificant

    @property
    def right_insignificant(self) -> bool:
        return self.right.parent.parent.insignificant

    @property
    def highlight_index(self) -> int:
        return int(js_max(self.left_highlight_index, self.right_highlight_index))

    @property
    def x0(self) -> float:
        return self.left.x + self.left.width

    @property
    def x1(self) -> float:
        return self.right.x

    @property
    def y0(self) -> float:
        return self.left.y

    @property
    def y1(self) -> float:
        return self.right.y

    @property
    def h0(self) -> float:
        return self.left.height

    @property
    def h1(self) -> float:
        return self.right.height

    @property
    def avg_height(self) -> float:
        return (self.h0 + self.h1) / 2

    @property
    def path(self) -> str:
        x0, x1, y0, y1, h0, h1 = self.x0, self.x1, self.y0, self.y1, self.h0, self.h1
        threshold = 1e-6
        y0 = 0 if y0 < threshold else y0
        y1 = 0 if y1 < threshold else y1
        y2 = y0 + h0
        y3 = y1 + h1
        cpx = (x0 + x1) / 2
        f = js_number_to_string
        return (
            f"M{f(x0)},{f(y2)}"
            f"C{f(cpx)},{f(y2)},{f(cpx)},{f(y3)},{f(x1)},{f(y3)}"
            f"L{f(x1)},{f(y1)}"
            f"C{f(cpx)},{f(y1)},{f(cpx)},{f(y0)},{f(x0)},{f(y0)}"
            "Z"
        )

    def remove(self) -> None:
        self.left.link = None
        self.right.link = None
