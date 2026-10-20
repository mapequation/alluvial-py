"""Replay every fixture (v1 and v2) through ``alluvial.io`` + ``alluvial.engine`` and compare the full engine state.

The dump mirrors ``tools/ts-fixtures/harness.ts`` (``dumpScenario``/``dumpModule``/``dumpLink``) field by field,
including the pass-1 and sort-key snapshots of the last ``update_layout`` call.
"""

from __future__ import annotations

import math
import os
import re
import warnings
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES_DIR, TESTS_DIR, V2_SCENARIOS, assert_matches, load_fixture

from alluvial._jscompat import js_max
from alluvial.engine import DiagramStore
from alluvial.engine.depth import MODULE
from alluvial.engine.diagram import Diagram
from alluvial.engine.module import Module
from alluvial.engine.network import TreeNode
from alluvial.geometry import js_ceil
from alluvial.io import read
from alluvial.layout import LayoutOptions, _distinct_ids

# Fields that describe the scenario rather than the engine state.
IGNORED = frozenset(
    {"formatVersion", "scenario", "group", "variant", "description", "features", "inputs", "warnings"}
)

# The readers warn about identifiers shared by several nodes (states-tree__name*); the engine accepts them.
pytestmark = pytest.mark.filterwarnings("ignore:.*identifier.*shared:UserWarning")


class Trace:
    """The pass-1 and sort-key snapshots of the last ``update_layout``, keyed by ``id(obj)`` like the harness's
    object-keyed Maps. The snapshotted objects are kept alive (``_alive``), so that an object created later (a
    streamline node re-created by a colour op that runs no layout) cannot reuse a snapshotted ``id``."""

    def __init__(self) -> None:
        self.pass1_modules: dict[int, dict[str, Any]] = {}
        self.pass1_groups: dict[int, dict[str, Any]] = {}
        self.sort_keys: dict[int, float] = {}
        self.calls = 0
        self._alive: dict[str, list[Any]] = {"pass1": [], "sort": []}

    def __call__(self, stage: str, diagram: Diagram) -> None:
        if stage == "pass1":
            self.calls += 1
            self.pass1_modules = {}
            self.pass1_groups = {}
            alive = self._alive["pass1"] = []
            for network in diagram.children:
                for module in network.children:
                    if not module.is_visible:
                        continue
                    alive.append(module)
                    self.pass1_modules[id(module)] = {
                        **_rect(module),
                        "margin": module.margin,
                        "index": module.index,
                    }
                    for group in module.children:
                        alive.append(group)
                        self.pass1_groups[id(group)] = _rect(group)
        else:
            self.sort_keys = {}
            alive = self._alive["sort"] = []
            for network in diagram.children:
                for module in network.children:
                    for group in module.children:
                        for branch in group.children:
                            for sn in branch.children:
                                alive.append(sn)
                                self.sort_keys[id(sn)] = sn.opposite_streamline_position


def _rect(n: Any) -> dict[str, float]:
    return {"x": n.x, "y": n.y, "width": n.width, "height": n.height}


def _xy(p: tuple[float, float]) -> dict[str, float]:
    return {"x": p[0], "y": p[1]}


def _size_fn(network: Any, max_network_flow: float, module_size: str):
    num_leaf_nodes = network.num_leaf_nodes
    if module_size == "flow":
        return lambda n: n.flow / max_network_flow
    return lambda n: n.num_leaf_nodes / num_leaf_nodes


def _label_names(module: Module, n: int, aggregate: bool, highlight: bool = False) -> list[dict[str, Any]]:
    names = []
    for node in module.get_largest_leaf_nodes(n, aggregate):
        entry = {"name": node.name, "nodeId": node.node_id, "stateId": node.state_id, "flow": node.flow}
        if highlight:
            # v2 labelNameHighlight: the aggregated copies have no `insignificant` (TS: not an own property)
            entry["highlightIndex"] = node.highlight_index
            entry["insignificant"] = getattr(node, "insignificant", None)
        names.append(entry)
    return names


def _dump_module(
    module: Module, trace: Trace, label_options: dict[str, Any], name_highlight: bool = False
) -> dict[str, Any]:
    p1 = trace.pass1_modules.get(id(module))
    visible = module.is_visible
    height_per_line = label_options["fontSize"] * 1.8
    max_lines = js_ceil(module.height / height_per_line)
    if max_lines != 0 and max_lines % 2 == 0:
        max_lines -= 1
    aggregate = label_options["aggregateStateNames"]
    groups = []
    for group in module.children:
        g1 = trace.pass1_groups.get(id(group))
        branches = []
        for branch in group.children:
            sns = []
            for sn in branch.children:
                opp = sn.opposite
                sort_key = trace.sort_keys.get(id(sn))
                opp_module = opp.get_ancestor(MODULE) if opp is not None else None
                sns.append(
                    {
                        "id": sn.current_id,
                        "sourceId": sn.source_id,
                        "targetId": sn.target_id,
                        "dangling": sn.is_dangling,
                        "flow": sn.flow,
                        "numLeafNodes": sn.num_leaf_nodes,
                        **_rect(sn),
                        "sortKey": sort_key,
                        "linked": sn.link is not None,
                        "opposite": None
                        if opp is None
                        else {
                            "networkId": opp.network_id,
                            "id": opp.current_id,
                            "moduleId": opp_module.module_id if opp_module is not None else None,
                        },
                    }
                )
            branches.append(
                {
                    "side": "left" if branch.is_left else "right",
                    "flow": branch.flow,
                    "numLeafNodes": branch.num_leaf_nodes,
                    **_rect(branch),
                    "streamlineNodes": sns,
                }
            )
        groups.append(
            {
                "id": group.id,
                "highlightIndex": group.highlight_index,
                "insignificant": group.insignificant,
                "flow": group.flow,
                "numLeafNodes": group.num_leaf_nodes,
                **_rect(group),
                "pass1": g1,
                "branches": branches,
            }
        )
    return {
        "moduleId": module.module_id,
        "id": module.id,
        "path": module.path,
        "moduleLevel": module.module_level,
        "maxModuleLevel": module.max_module_level,
        "index": module.index,
        "flow": module.flow,
        "numLeafNodes": module.num_leaf_nodes,
        "meanNodeId": module.mean_node_id,
        "enterFlow": module.enter_flow,
        "exitFlow": module.exit_flow,
        "visible": visible,
        "highlightIndex": module.highlight_index,
        "margin": module.margin,
        **_rect(module),
        "pass1": None
        if p1 is None
        else {
            "margin": p1["margin"],
            "index": p1["index"],
            **{k: p1[k] for k in ("x", "y", "width", "height")},
        },
        "label": {
            "shown": visible and label_options["showModuleNames"] and module.text_anchor is not None,
            "textAnchor": module.text_anchor,
            "namePosition": _xy(module.name_position),
            "idPosition": _xy(module.id_position),
            "customName": module.name,
            "maxLines": max_lines,
            "names": _label_names(module, max_lines, aggregate, name_highlight) if max_lines > 0 else [],
            "namesSingleLine": _label_names(module, 5, aggregate, name_highlight),
        },
        "groups": groups,
    }


def _dump_link(link: Any) -> dict[str, Any]:
    def end(sn: Any) -> dict[str, Any]:
        group = sn.parent.parent
        module = sn.get_ancestor(MODULE)
        return {
            "networkId": sn.network_id,
            "moduleId": module.module_id if module is not None else None,
            "groupHighlightIndex": group.highlight_index,
            "groupInsignificant": group.insignificant,
            "streamlineNodeId": sn.current_id,
        }

    return {
        "id": link.id,
        "left": end(link.left),
        "right": end(link.right),
        "x0": link.x0,
        "y0": link.y0,
        "h0": link.h0,
        "x1": link.x1,
        "y1": link.y1,
        "h1": link.h1,
        "avgHeight": link.avg_height,
        "highlightIndex": link.highlight_index,
        "leftHighlightIndex": link.left_highlight_index,
        "rightHighlightIndex": link.right_highlight_index,
        "path": link.path,
    }


def _leaf_sort_key(leaf: Any) -> tuple[Any, str]:
    return (leaf.state_id if leaf.state_id is not None else leaf.node_id, leaf.identifier)


def dump_store(
    store: DiagramStore, trace: Trace, fx_inputs: dict[str, Any], files: list[Any]
) -> dict[str, Any]:
    """The fixture dict (minus the scenario description fields) for a replayed store."""
    diagram = store.diagram
    o = store.options
    height, module_width, streamline_fraction, zero_margins = (
        o.height,
        o.module_width,
        o.streamline_fraction,
        o.zero_margins,
    )
    num_networks = len(diagram.children)
    streamline_width = streamline_fraction * module_width
    network_width = module_width + streamline_width
    total_width = network_width * num_networks - streamline_width
    max_network_flow = js_max(*(n.flow for n in diagram.children))

    total_margins, visible_flows, visible_counts = [], [], []
    for network in diagram.children:
        size = _size_fn(network, max_network_flow, o.module_size)
        tm, vf, vc = 0, 0, 0
        for module in network.children:
            if not module.is_visible:
                continue
            tm += trace.pass1_modules[id(module)]["margin"]
            vf += size(module)
            vc += 1
        total_margins.append(tm)
        visible_flows.append(vf)
        visible_counts.append(vc)
    max_total_margin = js_max(*total_margins)
    usable_height = height - max_total_margin
    max_margin_fraction = 0 if zero_margins else 0.2
    margin_fraction = max_total_margin / height
    capped, scale, scaled = False, None, None
    if margin_fraction > max_margin_fraction:
        capped = True
        scale = 0 if zero_margins else (max_margin_fraction * height) / max_total_margin
        scaled = max_total_margin * scale
        usable_height = height - scaled

    checked = 0
    for network in diagram.children:
        size = _size_fn(network, max_network_flow, o.module_size)
        for module in network.children:
            if module.is_visible:
                expected = size(module) * usable_height
                assert module.height == expected or (math.isnan(module.height) and math.isnan(expected))
                checked += 1

    label_options = fx_inputs["labelOptions"]
    name_highlight = bool(fx_inputs.get("labelNameHighlight"))
    split = bool(fx_inputs.get("split"))
    sources = fx_inputs.get("networkSources") or list(range(num_networks))
    networks = []
    for i, network in enumerate(diagram.children):
        file = next(f for f in files if f.id == network.network_id)
        leaves = sorted(network.leaf_nodes(), key=_leaf_sort_key)
        leaf_rows = [
            [
                leaf.identifier,
                leaf.node_id,
                leaf.state_id,
                leaf.module_id,
                leaf.module_level,
                leaf.highlight_index,
                leaf.insignificant,
            ]
            for leaf in leaves
        ]
        hierarchy = [
            {
                "type": "tree",
                "path": node.path,
                "moduleLevel": node.module_level,
                "isLeaf": node.is_leaf,
                "maxModuleLevel": node.max_module_level,
                **_rect(node),
            }
            if isinstance(node, TreeNode)
            else {"type": "module", "moduleId": node.module_id}
            for node in network.hierarchical_children
        ]
        networks.append(
            {
                "networkId": network.network_id,
                "name": network.name,
                "index": i,
                "file": {
                    "path": fx_inputs["files"][sources[i]],
                    "format": file.format,
                    "numTopModules": file.num_top_modules,
                    "numLevels": file.num_levels,
                    "isStateNetwork": file.is_state_network,
                    "directed": file.directed,
                    "codelength": file.codelength,
                    "numNodes": len(file.nodes),
                    **({"layerId": file.layer_id, "originalId": file.original_id} if split else {}),
                },
                **_rect(network),
                "flow": network.flow,
                "numLeafNodes": network.num_leaf_nodes,
                "moduleFlowThreshold": network.flow_threshold,
                "isCustomSorted": network.is_custom_sorted,
                # TS throws for a network without leaves (the harness writes null); Python returns False
                "isHigherOrder": network.is_higher_order
                if next(network.leaf_nodes(), None) is not None
                else None,
                "namePosition": _xy(network.name_position),
                "totalMargin": total_margins[i],
                "visibleFlow": visible_flows[i],
                "numVisibleModules": visible_counts[i],
                "numModules": len(network.children),
                "modules": [_dump_module(m, trace, label_options, name_highlight) for m in network.children],
                "numLinksAboveZero": len(network.get_links(0)),
                "links": [_dump_link(link) for link in network.get_links(o.streamline_threshold)],
                "hierarchy": hierarchy,
                "identifiersUnique": len({row[0] for row in leaf_rows}) == len(leaf_rows),
                "leafColumns": [
                    "identifier",
                    "nodeId",
                    "stateId",
                    "moduleId",
                    "moduleLevel",
                    "highlightIndex",
                    "insignificant",
                ],
                "leaves": leaf_rows,
            }
        )

    return {
        "diagram": {
            **_rect(diagram),
            "flow": diagram.flow,
            "numNetworks": num_networks,
            "maxNetworkFlow": max_network_flow,
            "streamlineWidth": streamline_width,
            "networkWidth": network_width,
            "totalWidth": total_width,
            "totalMargins": total_margins,
            "maxTotalMargin": max_total_margin,
            "marginFractionOfHeight": margin_fraction,
            "maxMarginFractionOfHeight": max_margin_fraction,
            "marginCapped": capped,
            "moduleMarginScale": scale,
            "scaledTotalMargin": scaled,
            "usableHeight": usable_height,
            "visibleFlows": visible_flows,
            "visibleModuleCounts": visible_counts,
            "updateLayoutCalls": trace.calls,
            "usableHeightCheckedModules": checked,
        },
        "highlightColors": list(store.highlight_colors),
        "defaultHighlightColor": store.default_highlight_color,
        "networks": networks,
    }


def read_fixture_inputs(inputs: dict[str, Any], *, node_metadata: bool = True) -> list[Any]:
    """The final network files of a fixture: read ``inputs.files``, assign ``inputs.nodeMetadata`` (v2), split the
    ``inputs.split`` files into layers (v2, increasing index, in place), then pin ids and names from ``inputs``."""
    parsed = [read(TESTS_DIR / rel, identifier=inputs["identifier"]) for rel in inputs["files"]]
    metadata = inputs.get("nodeMetadata") if node_metadata else None
    if metadata:
        for nf, rows in zip(parsed, metadata, strict=True):
            assert len(rows) == len(nf.nodes)
            for node, md in zip(nf.nodes, rows):
                node.metadata = md
    split = set(inputs.get("split") or ())
    # the harness's input ids: file stems, a repeated one renamed `<stem>_<k>` (layout()'s rule)
    for nf, input_id in zip(parsed, _distinct_ids([nf.id for nf in parsed]), strict=True):
        nf.id = input_id
    files = []
    for i, nf in enumerate(parsed):
        if i in split:
            from alluvial.io import split_layers

            files.extend(split_layers(nf))
        else:
            files.append(nf)
    assert len(files) == len(inputs["networkIds"])
    for nf, network_id, name in zip(files, inputs["networkIds"], inputs["networkNames"]):
        nf.id = network_id
        nf.name = name
    return files


def _store(inputs: dict[str, Any], trace: Trace) -> DiagramStore:
    # `options` are the store options at the end; `initialOptions` (present only when a setOption op changed
    # them) are the ones the diagram was built with.
    return DiagramStore(LayoutOptions.from_ts(inputs.get("initialOptions", inputs["options"])), trace=trace)


def replay_fixture(fx: dict[str, Any]) -> tuple[DiagramStore, Trace, list[Any]]:
    inputs = fx["inputs"]
    files = read_fixture_inputs(inputs)
    trace = Trace()
    store = _store(inputs, trace)
    with warnings.catch_warnings():
        # a refusal the fixture expects (planted-ftree__moveHidden) warns like the TS console.warn it recorded
        for message in fx.get("warnings", ()):
            if message.startswith("Can't move module"):
                warnings.filterwarnings("ignore", message=re.escape(message), category=UserWarning)
        store.replay(files, inputs["operations"])
    return store, trace, files


def highlight_label_of(groups: list[list[Any]]):
    """The ``highlight`` macro's labels (``[[label, identifiers], ...]``) as ``label_of_leaf`` for
    ``DiagramStore.apply_highlight``."""
    label_of = {identifier: k for k, (_, identifiers) in enumerate(groups) for identifier in identifiers}
    return lambda leaf: label_of.get(leaf.identifier)


def replay_fixture_with_macros(fx: dict[str, Any]) -> tuple[DiagramStore, Trace, list[Any]]:
    """Replay with the Python macro implementations instead of the concrete ops the TS harness recorded:
    ``moduleLevel`` through ``apply_module_level`` (it must issue exactly the recorded ops) and ``highlight``
    through ``apply_highlight`` (metadata written onto the leaves after the build, not onto the input nodes), and
    ``moduleOrder`` through ``apply_module_order`` (at most one ``setModuleOrder`` op)."""
    inputs = fx["inputs"]
    # several macros can share an atOperation (one that issued no op, e.g. moduleLevel with nothing to expand)
    macros: dict[int, list[dict[str, Any]]] = {}
    for m in inputs.get("macros", ()):
        macros.setdefault(m["atOperation"], []).append(m)
    has_highlight = any(m["op"]["op"] == "highlight" for ms in macros.values() for m in ms)
    files = read_fixture_inputs(inputs, node_metadata=not has_highlight)
    trace = Trace()
    store = _store(inputs, trace)
    ops = inputs["operations"]
    assert ops[0]["op"] == "setNetworks"
    store.set_networks(files)
    i = 1
    while i < len(ops) or macros.get(i):
        if not macros.get(i):
            store.apply(ops[i])
            i += 1
            continue
        macro = macros[i].pop(0)
        op = macro["op"]
        issued = ops[i : i + macro["numOperations"]]
        if op["op"] == "moduleLevel":
            assert store.apply_module_level(op["levels"]) == issued
        elif op["op"] == "moduleOrder":
            assert store.apply_module_order((ni, ids) for ni, ids in op["order"]) == issued
        else:
            assert op["op"] == "highlight"
            indices = store.apply_highlight(highlight_label_of(op["groups"]), op["colors"])
            assert indices == [store.get_highlight_index(c) for c in op["colors"]]
        i += macro["numOperations"]
    return store, trace, files


def test_engine_fixture(scenario: str) -> None:
    fx = load_fixture(scenario)
    store, trace, files = replay_fixture(fx)
    actual = dump_store(store, trace, fx["inputs"], files)
    res = assert_matches(actual, fx, ignore=IGNORED)
    assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"


def _streamline_ids(value: Any, key: str = "") -> list[str]:
    if isinstance(value, dict):
        return [x for k, v in value.items() if k != "description" for x in _streamline_ids(v, k)]
    if isinstance(value, list):
        return [x for v in value for x in _streamline_ids(v, key)]
    return [value] if isinstance(value, str) else []


def test_no_fixture_has_a_null_streamline_id() -> None:
    """E6: duplicate identifiers link only the registered leaf, so no streamline node gets a ``NULL--`` id."""
    paths = sorted(FIXTURES_DIR.rglob("*.json"))
    assert paths
    bad = [p.name for p in paths if any(s.startswith("NULL--") for s in _streamline_ids(load_fixture(p)))]
    assert bad == []


MACRO_SCENARIOS = [s for s in V2_SCENARIOS if load_fixture(s)["inputs"].get("macros")]


@pytest.mark.parametrize("scenario_with_macros", MACRO_SCENARIOS)
def test_engine_fixture_macros(scenario_with_macros: str) -> None:
    """The Python ``module_level``/``highlight`` helpers reproduce the harness macros (ops and final state)."""
    fx = load_fixture(scenario_with_macros)
    store, trace, files = replay_fixture_with_macros(fx)
    actual = dump_store(store, trace, fx["inputs"], files)
    res = assert_matches(actual, fx, ignore=IGNORED)
    assert res.non_bitwise == 0


# Opt-in: the `large` scenarios (not committed, e.g. science-stree__level2, ~40 MB), generated with
#   node tools/ts-fixtures/generate.mjs --large --only science-stree__level2 --out DIR
# and replayed with ALLUVIAL_LARGE_FIXTURES=DIR (every DIR/*.json; both the recorded ops and the Python macros).
LARGE_DIR = os.environ.get("ALLUVIAL_LARGE_FIXTURES")
LARGE_FIXTURES = sorted(Path(LARGE_DIR).glob("*.json")) if LARGE_DIR else []


@pytest.mark.skipif(
    not LARGE_FIXTURES, reason="set ALLUVIAL_LARGE_FIXTURES=DIR (generate.mjs --large --out DIR)"
)
@pytest.mark.parametrize("path", LARGE_FIXTURES, ids=[p.stem for p in LARGE_FIXTURES])
@pytest.mark.parametrize("with_macros", [False, True], ids=["ops", "macros"])
def test_engine_large_fixture(path: Path, with_macros: bool) -> None:
    fx = load_fixture(path)
    if with_macros and not fx["inputs"].get("macros"):
        pytest.skip("no macros")
    store, trace, files = (replay_fixture_with_macros if with_macros else replay_fixture)(fx)
    actual = dump_store(store, trace, fx["inputs"], files)
    res = assert_matches(actual, fx, ignore=IGNORED)
    assert res.non_bitwise == 0, f"{res.non_bitwise} floats differ from TS in the last bits"
