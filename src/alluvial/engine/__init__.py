"""Faithful port of the TS engine (``packages/alluvial-diagram/src/alluvial``). Internal; never imports matplotlib.

One module per TS class, same class names, snake_case members, and the same iteration and mutation order.
"""

from __future__ import annotations

from .alluvial_node import AlluvialNode, Layout
from .branch import Branch
from .diagram import Diagram
from .highlight_group import NOT_HIGHLIGHTED, HighlightGroup
from .leaf_node import LeafNode
from .module import Module
from .network import Network
from .side import LEFT, RIGHT
from .store import DiagramStore
from .streamline_link import StreamlineLink
from .streamline_node import StreamlineNode

__all__ = [
    "LEFT",
    "NOT_HIGHLIGHTED",
    "RIGHT",
    "AlluvialNode",
    "Branch",
    "Diagram",
    "DiagramStore",
    "HighlightGroup",
    "Layout",
    "LeafNode",
    "Module",
    "Network",
    "StreamlineLink",
    "StreamlineNode",
]
