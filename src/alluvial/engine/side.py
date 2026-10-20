"""Port of ``alluvial/Side.ts``."""

from __future__ import annotations

LEFT = -1
RIGHT = 1


def side_to_string(side: int) -> str:
    return "left" if side == LEFT else "right"


def opposite(side: int) -> int:
    return -side
