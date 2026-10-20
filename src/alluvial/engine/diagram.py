"""Port of ``alluvial/Diagram.ts``: the root node, ``calc_flow`` and ``update_layout``.

``update_layout`` keeps the TS traversals (pre-order pass 1, margin cap, justify, branch sort, post-order pass 2)
and their exact float operation order. Spec: docs/dev/port-notes/layout.md §4.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from .._jscompat import js_max
from ._utils import difference_index, sort_by_number
from .alluvial_node import AlluvialNode
from .branch import Branch
from .depth import BRANCH, LEAF_NODE, MODULE, NETWORK, ROOT
from .highlight_group import HighlightGroup
from .module import Module
from .network import Network
from .streamline_node import StreamlineNode
from .tree import Tree

if TYPE_CHECKING:
    from ..io.types import NetworkFile
    from ..layout import LayoutOptions

GetNodeSize = Callable[[Any], float]
LayoutTrace = Callable[[str, "Diagram"], None]


class Diagram(AlluvialNode):
    __slots__ = ("flow_threshold",)

    depth = ROOT

    def __init__(self, networks: Sequence[NetworkFile] = ()) -> None:
        super().__init__(None, "", "root")
        self.flow_threshold: float = 0
        for network in networks:
            self.add_network(network)

    def add_network(self, network: NetworkFile) -> None:
        if any(n.network_id == network.id for n in self.children):
            raise ValueError(f"Network with id {network.id} already exists")
        Network.create(self, network).add_nodes(network.nodes)

    def get_network(self, network_id: str) -> Network | None:
        return next((n for n in self.children if n.network_id == network_id), None)

    def calc_flow(self) -> None:
        def callback(node: Any, i: int, nodes: list[Any]) -> None:
            node.flow = node.child_flow

        self.for_each_depth_first_post_order_while(lambda node: node.depth < LEAF_NODE, callback)

    def update_layout(self, options: LayoutOptions, trace: LayoutTrace | None = None) -> None:
        """Lay out every node (TS ``Diagram.updateLayout``).

        ``trace``, if given, is called as ``trace("pass1", diagram)`` after pass 1 and ``trace("pass2", diagram)``
        just before pass 2 (test instrumentation, mirroring the fixture harness).
        """
        height = options.height
        streamline_fraction = options.streamline_fraction
        module_width = options.module_width
        flow_threshold = options.flow_threshold
        margin_exponent = options.margin_exponent
        zero_margins = options.zero_margins
        vertical_align = options.vertical_align
        module_size = options.module_size
        sort_modules_by = options.sort_modules_by

        num_networks = len(self.children)
        if not num_networks:
            return

        streamline_width = streamline_fraction * module_width
        network_width = module_width + streamline_width
        total_width = network_width * num_networks - streamline_width

        self.width = total_width
        self.height = height
        self.flow_threshold = flow_threshold

        for network in self.children:
            network.update_flow_threshold(flow_threshold)

        max_network_flow = js_max(*(network.flow for network in self.children))

        total_margins = [0.0] * num_networks
        visible_flows = [0.0] * num_networks
        visible_modules = [0] * num_networks

        state: dict[str, Any] = {
            "x": 0.0,
            "y": height,
            "network_index": 0,
            "get_node_size": None,
            "module_height": 0.0,
            "module_margin": 0.0,
        }

        def pass1(node: Any, i: int, nodes: list[Any]) -> None:
            if isinstance(node, Network):
                state["get_node_size"] = _node_size_fn(node, max_network_flow, module_size)
                state["network_index"] = i

                visible = [m for m in node.children if m.is_visible]
                invisible = [m for m in node.children if not m.is_visible]

                if not node.is_custom_sorted:
                    order = _node_order_fn(node, max_network_flow, sort_modules_by)
                    for index, module in enumerate(Tree(visible, order).sort().flatten()):
                        module.index = index
                    visible.sort(key=lambda m: m.index)

                # fix round E7: index the visible modules in drawn order also when the order is custom, and zero
                # the margin of hidden modules (not laid out; a stale margin would only be scaled by the cap).
                for index, module in enumerate(visible):
                    module.index = index
                for module in invisible:
                    module.margin = 0

                node.children = visible + invisible

                if i > 0:
                    state["x"] += network_width
                state["y"] = height
            elif isinstance(node, Module) and state["get_node_size"] is not None:
                node.children.sort(key=lambda g: (g.insignificant, g.highlight_index))
                if i + 1 < len(nodes) and not zero_margins:
                    margin = 2 ** (margin_exponent - 2 * difference_index(node.path, nodes[i + 1].path))
                else:
                    margin = 0
                node_size = state["get_node_size"](node)
                module_height = node_size * height
                state["module_height"] = module_height
                state["y"] -= module_height
                node.margin = margin
                node.set_layout(state["x"], state["y"], module_width, module_height)
                state["module_margin"] = margin
                state["y"] -= margin
                network_index = state["network_index"]
                total_margins[network_index] += margin
                visible_flows[network_index] += node_size
                visible_modules[network_index] += 1
            elif isinstance(node, HighlightGroup) and state["get_node_size"] is not None:
                if i == 0:
                    state["y"] += state["module_height"] + state["module_margin"]
                group_height = state["get_node_size"](node) * height
                state["y"] -= group_height
                node.set_layout(state["x"], state["y"], module_width, group_height)
                if i + 1 == len(nodes):
                    state["y"] -= state["module_margin"]

        self.for_each_depth_first_pre_order_while(
            lambda node: (
                node.depth < MODULE
                or (isinstance(node, Module) and node.is_visible)
                or isinstance(node, HighlightGroup)
            ),
            pass1,
        )

        if trace is not None:
            trace("pass1", self)

        max_total_margin = js_max(*total_margins)
        usable_height = height - max_total_margin

        max_margin_fraction_of_height = 0 if zero_margins else 0.2
        margin_fraction_of_height = max_total_margin / height

        if margin_fraction_of_height > max_margin_fraction_of_height:
            module_margin_scale = (
                0 if zero_margins else (max_margin_fraction_of_height * height) / max_total_margin
            )

            def cap(node: Any, i: int, nodes: list[Any]) -> None:
                if isinstance(node, Module):
                    node.margin *= module_margin_scale

            self.for_each_depth_first_pre_order_while(lambda node: node.depth <= MODULE, cap)

            scaled_total_margin = max_total_margin * module_margin_scale
            usable_height = height - scaled_total_margin

        if vertical_align == "justify":
            justify: dict[str, Any] = {
                "total_margin": max_total_margin,
                "visible_flow": js_max(*visible_flows),
                "missing_flow": 0.0,
                "missing_margin": 0.0,
                "num_margins": 0,
            }

            def justify_cb(node: Any, i: int, nodes: list[Any]) -> None:
                if isinstance(node, Network):
                    justify["total_margin"] = total_margins[i]
                    justify["num_margins"] = visible_modules[i] - 1
                    justify["visible_flow"] = visible_flows[i]
                    justify["missing_flow"] = 1 - justify["visible_flow"]
                    justify["missing_margin"] = justify["missing_flow"] * usable_height
                elif isinstance(node, Module) and node.margin > 0:
                    node.margin *= max_total_margin / justify["total_margin"]
                    if justify["num_margins"] > 0:
                        node.margin += justify["missing_margin"] / justify["num_margins"]

            self.for_each_depth_first_pre_order_while(
                lambda node: node.depth < MODULE or (isinstance(node, Module) and node.is_visible),
                justify_cb,
            )

        def sort_branches(node: Any, i: int, nodes: list[Any]) -> None:
            if isinstance(node, Branch):
                sort_by_number(node.children, lambda sn: sn.opposite_streamline_position)

        self.for_each_depth_first_pre_order_while(lambda node: node.depth <= BRANCH, sort_branches)

        if trace is not None:
            trace("pass2", self)

        state["x"] = 0.0
        state["y"] = height
        state["get_node_size"] = None

        def pass2(node: Any, i: int, nodes: list[Any]) -> None:
            if isinstance(node, StreamlineNode):
                if state["get_node_size"] is None:
                    network = node.get_ancestor(NETWORK)
                    if network is None:
                        return
                    state["get_node_size"] = _node_size_fn(network, max_network_flow, module_size)
                node_height = state["get_node_size"](node) * usable_height
                state["y"] -= node_height
                node.set_layout(state["x"], state["y"], module_width, node_height)
            elif isinstance(node, Branch) and state["get_node_size"] is not None:
                branch_height = state["get_node_size"](node) * usable_height
                node.set_layout(state["x"], state["y"], module_width, branch_height)
                if node.is_left:
                    state["y"] += branch_height
            elif isinstance(node, HighlightGroup) and state["get_node_size"] is not None:
                node.set_layout(
                    state["x"], state["y"], module_width, state["get_node_size"](node) * usable_height
                )
            elif isinstance(node, Module) and state["get_node_size"] is not None:
                node.set_layout(
                    state["x"], state["y"], module_width, state["get_node_size"](node) * usable_height
                )
                state["y"] -= node.margin
            elif isinstance(node, Network):
                node.set_layout(state["x"], 0, module_width, height)
                state["x"] += network_width
                state["y"] = height
                state["get_node_size"] = None
            elif isinstance(node, Diagram):
                node.set_layout(0, 0, total_width, height)

        self.for_each_depth_first_post_order_while(
            lambda node: node.depth != MODULE or (isinstance(node, Module) and node.is_visible),
            pass2,
        )


def _node_size_fn(network: Network, max_flow: float, module_size: str) -> GetNodeSize:
    num_leaf_nodes = network.num_leaf_nodes
    if module_size == "flow":
        return lambda node: node.flow / max_flow
    if module_size == "nodes":
        return lambda node: node.num_leaf_nodes / num_leaf_nodes
    raise ValueError("Module size must be either 'flow' or 'nodes'.")


def _node_order_fn(network: Network, max_flow: float, sort_modules_by: str) -> GetNodeSize:
    num_leaf_nodes = network.num_leaf_nodes
    if sort_modules_by == "flow":
        return lambda node: node.flow / max_flow
    if sort_modules_by == "nodes":
        return lambda node: node.num_leaf_nodes / num_leaf_nodes
    if sort_modules_by == "highlight_index":
        return lambda node: -node.highlight_index
    if sort_modules_by == "node_id":
        return lambda node: node.mean_node_id
    raise ValueError("Module order must be either 'flow', 'nodes', 'node_id' or 'highlight_index'.")
