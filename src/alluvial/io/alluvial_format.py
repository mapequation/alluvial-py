"""Saved diagrams: "alluvial network files", formatVersion 1 (port of the TS ``parsers/alluvial-format.ts``).

A saved diagram is one Infomap-JSON file per network, loose or in a zip. Each file is a superset of
``infomap -o json`` output: Infomap's top-level keys are passed through, and the file adds ``name``, ``colors``
(the palette) and three node keys (``identifier``, ``highlightIndex``, ``moduleLevel``). Everything else is in one
namespaced block that other readers ignore::

    "alluvial": {
      "format": "alluvial-network", "formatVersion": 1, "generator": "...",
      "diagram": {"saveId", "position", "numNetworks", "colorScheme", "colorTone", "colorOffset", "options"},
      "network": {"moduleNames"?, "moduleOrder"?}
    }

The diagram part is the same in every file of one save (tied together by ``saveId``); the network part belongs to
the file's network. ``serialize_diagram`` writes the same text as the TS ``serializeDiagram`` byte for byte (the
fixtures prove it), and ``DiagramStore.open_networks`` restores the same state as the TS ``openNetworks``.
Spec: docs/dev/saveload-plan.md §4.
"""

from __future__ import annotations

import math
import re
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .._jscompat import js_json_stringify, js_number_to_string, js_own_keys_order

if TYPE_CHECKING:
    from ..engine.network import Network
    from ..engine.store import DiagramStore
    from .types import InfomapModule, NetworkFile

__all__ = [
    "ALLUVIAL_FORMAT",
    "ALLUVIAL_FORMAT_VERSION",
    "DISPLAY_OPTION_DEFAULTS",
    "LAYOUT_OPTION_KEYS",
    "SAVED_OPTION_KEYS",
    "AlluvialRestore",
    "read_alluvial_metadata",
    "serialize_diagram",
    "sort_by_saved_position",
]

ALLUVIAL_FORMAT = "alluvial-network"
ALLUVIAL_FORMAT_VERSION = 1

#: Infomap's top-level keys that a saved file copies from its input (TS name -> ``NetworkFile`` field), in order.
PASS_THROUGH_KEYS: dict[str, str] = {
    "version": "version",
    "args": "args",
    "startedAt": "started_at",
    "completedIn": "completed_in",
    "codelength": "codelength",
    "relativeCodelengthSavings": "relative_codelength_savings",
    "directed": "directed",
    "flowModel": "flow_model",
    "higherOrder": "higher_order",
    "stateLevel": "state_level",
    "bipartiteStartId": "bipartite_start_id",
}

#: The TS store options a saved diagram carries (all but ``identifier`` and ``duration``), in the TS order.
SAVED_OPTION_KEYS: tuple[str, ...] = (
    "height",
    "marginExponent",
    "zeroMargins",
    "moduleWidth",
    "streamlineFraction",
    "streamlineThreshold",
    "streamlineOpacity",
    "flowThreshold",
    "defaultHighlightColor",
    "verticalAlign",
    "moduleSize",
    "sortModulesBy",
    "showModuleId",
    "showModuleNames",
    "multilineModuleNames",
    "showNetworkNames",
    "aggregateStateNames",
    "titleCaseModuleNames",
    "hierarchicalModules",
    "hierarchicalModuleOffset",
    "hierarchicalModuleOpacity",
    "dropShadow",
    "fontSize",
    "networkFontSize",
    "adaptiveFontSize",
    "showBipartiteNodes",
)

#: The saved options that are ``LayoutOptions`` fields (TS names).
LAYOUT_OPTION_KEYS: frozenset[str] = frozenset(
    {
        "height",
        "marginExponent",
        "zeroMargins",
        "moduleWidth",
        "streamlineFraction",
        "streamlineThreshold",
        "flowThreshold",
        "verticalAlign",
        "moduleSize",
        "sortModulesBy",
    }
)

#: The TS store's display options that the layout does not use (TS names and defaults). The engine store keeps them
#: (``DiagramStore.display_options``) so that a saved diagram writes them back unchanged.
DISPLAY_OPTION_DEFAULTS: dict[str, Any] = {
    "streamlineOpacity": 0.8,
    "showModuleId": False,
    "showModuleNames": True,
    "multilineModuleNames": True,
    "showNetworkNames": True,
    "aggregateStateNames": True,
    "titleCaseModuleNames": False,
    "hierarchicalModules": "shadow",
    "hierarchicalModuleOffset": 5,
    "hierarchicalModuleOpacity": 0.5,
    "dropShadow": False,
    "fontSize": 8,
    "networkFontSize": 10,
    "adaptiveFontSize": False,
}

_NOT_RESTORED = "options, module names and order were not restored"
_DIAGRAM_NOT_RESTORED = "the saved diagram options were not restored"


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _bool(v: Any) -> bool:
    return isinstance(v, bool)


def _string(v: Any) -> bool:
    return isinstance(v, str)


def _one_of(*values: str) -> Callable[[Any], bool]:
    return lambda v: isinstance(v, str) and v in values


#: The values a restore accepts (the same rules as the TS ``OPTION_RULES``).
OPTION_RULES: dict[str, Callable[[Any], bool]] = {
    "height": lambda v: _finite(v) and v > 0,
    "marginExponent": _finite,
    "zeroMargins": _bool,
    "moduleWidth": lambda v: _finite(v) and v > 0,
    "streamlineFraction": lambda v: _finite(v) and v >= 0,
    "streamlineThreshold": lambda v: _finite(v) and v >= 0,
    "streamlineOpacity": _finite,
    "flowThreshold": lambda v: _finite(v) and 0 <= v < 1,
    "defaultHighlightColor": _string,
    "verticalAlign": _one_of("bottom", "justify"),
    "moduleSize": _one_of("flow", "nodes"),
    "sortModulesBy": _one_of("flow", "nodes", "nodeId", "highlightIndex"),
    "showModuleId": _bool,
    "showModuleNames": _bool,
    "multilineModuleNames": _bool,
    "showNetworkNames": _bool,
    "aggregateStateNames": _bool,
    "titleCaseModuleNames": _bool,
    "hierarchicalModules": _one_of("none", "outline", "shadow"),
    "hierarchicalModuleOffset": _finite,
    "hierarchicalModuleOpacity": _finite,
    "dropShadow": _bool,
    "fontSize": _finite,
    "networkFontSize": _finite,
    "adaptiveFontSize": _bool,
    "showBipartiteNodes": _bool,
}

_UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_name(name: str) -> str:
    # JS replaces UTF-16 code units: a character outside the BMP is two of them
    return _UNSAFE_NAME_RE.sub(lambda m: "__" if ord(m.group()) > 0xFFFF else "_", name)


def _has_keys(metadata: Any) -> bool:
    """``metadata != null && Object.keys(metadata).length``."""
    if isinstance(metadata, (dict, list, str)):
        return len(metadata) > 0
    return False


def _js_integer(v: Any) -> bool:
    """``Number.isInteger(v)``."""
    return _finite(v) and v == int(v)


def _saved_path(leaf: Any) -> list[Any] | str:
    """TS ``TreePath.toSavedPath``: the path array, or the stree form when some level is insignificant."""
    tp = leaf.tree_path
    if not any(tp.insignificant):
        return list(tp.path_arr)
    return "".join(
        f"{js_number_to_string(n)}{';' if insig else ':'}"
        for n, insig in zip(tp.path_arr, tp.insignificant, strict=True)
    )


def _saved_node(leaf: Any) -> dict[str, Any]:
    node: dict[str, Any] = {"path": _saved_path(leaf), "flow": leaf._flow}
    if leaf.name is not None:
        node["name"] = leaf.name
    node["id"] = leaf.node_id
    if leaf.state_id is not None:
        node["stateId"] = leaf.state_id
    if leaf.layer_id is not None:
        node["layerId"] = leaf.layer_id
    if _has_keys(leaf.metadata):
        node["metadata"] = leaf.metadata
    node["identifier"] = leaf.identifier
    node["highlightIndex"] = leaf.highlight_index
    node["moduleLevel"] = leaf.module_level
    return node


def _module_record(module: InfomapModule) -> dict[str, Any]:
    """An ftree module record as the TS parser builds it (``@mapequation/infomap-parser``)."""
    return {
        "path": module.path,
        "enterFlow": module.enter_flow,
        "exitFlow": module.exit_flow,
        "numEdges": module.num_edges,
        "numChildren": module.num_children,
        "links": [{"source": link.source, "target": link.target, "flow": link.flow} for link in module.links],
    }


def _network_block(network: Network) -> dict[str, Any]:
    out: dict[str, Any] = {}
    names = {module.module_id: module.name for module in network.children if module.name}
    if names:
        out["moduleNames"] = names
    if network.is_custom_sorted:
        out["moduleOrder"] = [module.module_id for module in network.children]
    return out


def serialize_diagram(
    store: DiagramStore, *, generator: str, save_id: str | None = None
) -> list[tuple[str, str]]:
    """The store's diagram as one Infomap-JSON text per network, in diagram order, as ``(file name, text)``.

    A line-for-line port of the TS ``serializeDiagram`` (same names ``NN_<network name>.json``, key order, path
    encoding, option order and ``JSON.stringify(value, null, 2)`` text). ``save_id`` defaults to a random id.
    """
    if save_id is None:
        save_id = secrets.token_hex(4)
    networks = store.diagram.children
    colors = list(store.highlight_colors)
    options = store.get_options()
    out = []
    for position, network in enumerate(networks):
        nf = next((f for f in store.networks if f.id == network.network_id), None)
        value: dict[str, Any] = {}
        for key, attr in PASS_THROUGH_KEYS.items():
            v = getattr(nf, attr, None)
            if v is not None:
                value[key] = v
        value["name"] = network.name
        if colors:
            value["colors"] = colors
        value["nodes"] = [_saved_node(leaf) for leaf in network.built_leaf_nodes]
        if nf is not None and nf.raw_modules is not None:
            value["modules"] = nf.raw_modules
        elif nf is not None and nf.modules is not None:
            value["modules"] = [_module_record(m) for m in nf.modules]
        if nf is not None and nf.layers is not None:
            value["layers"] = nf.layers
        diagram: dict[str, Any] = {"saveId": save_id, "position": position, "numNetworks": len(networks)}
        if store.selected_scheme_name is not None:
            diagram["colorScheme"] = store.selected_scheme_name
        # both always written (#57): the c3 tone, and the offset (null for c3's default)
        diagram["colorTone"] = store.selected_tone
        diagram["colorOffset"] = store.selected_offset
        diagram["options"] = options
        value["alluvial"] = {
            "format": ALLUVIAL_FORMAT,
            "formatVersion": ALLUVIAL_FORMAT_VERSION,
            "generator": generator,
            "diagram": diagram,
            "network": _network_block(network),
        }
        name = f"{position:02d}_{_safe_name(str(network.name))}.json"
        out.append((name, js_json_stringify(value)))
    return out


@dataclass
class AlluvialRestore:
    """What ``read_alluvial_metadata`` found in the files of one diagram, ready to restore.

    Attributes
    ----------
    options : dict or None
        The checked saved options (TS names), when the files form one complete save; else ``None``.
    color_scheme : str or None
        The saved scheme name, when the files form one complete save and the name is known.
    color_tone : str or None
        The saved c3 tone, when the files form one complete save and the tone is a c3 tone.
    color_offset : float or None
        The saved c3 offset (``None`` for c3's default); meaningful only when ``has_color_offset``.
    has_color_offset : bool
        Whether the save has a valid ``colorOffset`` (a finite number or null; TS ``colorOffset !== undefined``).
    networks : list
        One entry per file: ``{"moduleNames": {...}, "moduleOrder": [...]}`` (each key optional), or ``None`` for a
        file without a valid formatVersion 1 block.
    warnings : list of str
        What cannot be restored (the TS ``openNetworks`` warnings, same text).
    """

    options: dict[str, Any] | None = None
    color_scheme: str | None = None
    color_tone: str | None = None
    color_offset: float | None = None
    has_color_offset: bool = False
    networks: list[dict[str, Any] | None] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _v1_blocks(files: Sequence[Any], warnings: list[str] | None) -> list[dict[str, Any] | None]:
    blocks: list[dict[str, Any] | None] = []
    for f in files:
        block = getattr(f, "alluvial", None)
        if not isinstance(block, dict) or block.get("format") != ALLUVIAL_FORMAT:
            blocks.append(None)
            continue
        version = block.get("formatVersion")
        if not _js_integer(version) or version < 1:
            if warnings is not None:
                warnings.append(
                    f"{f.name}: the saved diagram block has no valid formatVersion: {_NOT_RESTORED}"
                )
            blocks.append(None)
        elif version > ALLUVIAL_FORMAT_VERSION:
            if warnings is not None:
                warnings.append(
                    f"{f.name}: saved by a newer version (formatVersion {js_number_to_string(version)}): "
                    f"{_NOT_RESTORED}"
                )
            blocks.append(None)
        else:
            blocks.append(block)
    return blocks


def _diagram_block(block: dict[str, Any] | None) -> dict[str, Any] | None:
    raw = block.get("diagram") if block is not None else None
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("saveId"), str)
        or not _js_integer(raw.get("position"))
        or not _js_integer(raw.get("numNetworks"))
    ):
        return None
    return raw


def _network_block_of(block: dict[str, Any]) -> dict[str, Any]:
    raw = block.get("network")
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    names = raw.get("moduleNames")
    if isinstance(names, dict):
        out["moduleNames"] = {k: names[k] for k in js_own_keys_order(names) if isinstance(names[k], str)}
    order = raw.get("moduleOrder")
    if isinstance(order, list):
        out["moduleOrder"] = [m for m in order if isinstance(m, str)]
    return out


def _complete_save(diagrams: list[dict[str, Any] | None]) -> tuple[list[dict[str, Any]] | None, str | None]:
    valid = [d for d in diagrams if d is not None]
    if not valid:
        return None, None
    if len(valid) < len(diagrams) or any(d["saveId"] != valid[0]["saveId"] for d in valid):
        return None, f"the files are from different saves: {_DIAGRAM_NOT_RESTORED}"
    n = len(valid)
    positions = {d["position"] for d in valid}
    if (
        any(d["numNetworks"] != n for d in valid)
        or len(positions) != n
        or any(d["position"] < 0 or d["position"] >= n for d in valid)
    ):
        return None, (
            f"incomplete save: {n} of {js_number_to_string(valid[0]['numNetworks'])} networks: "
            f"{_DIAGRAM_NOT_RESTORED}"
        )
    return valid, None


def read_alluvial_metadata(files: Sequence[NetworkFile]) -> AlluvialRestore:
    """Read and check the ``alluvial`` blocks of the files of one diagram, in their final order (TS
    ``readAlluvialMetadata``; saveload-plan.md §4.4, §4.5).

    The network blocks apply per file; the diagram block (options, scheme, tone and offset) only when every file has a valid v1
    block of the same save and the positions are a permutation of ``0..n-1`` for ``n`` files. Problems give
    warnings (returned, not issued), never errors.
    """
    from .._palette import SCHEMES, TONES

    warnings: list[str] = []
    blocks = _v1_blocks(files, warnings)
    networks = [_network_block_of(b) if b is not None else None for b in blocks]
    valid, warning = _complete_save([_diagram_block(b) for b in blocks])
    if warning:
        warnings.append(warning)
    if valid is None:
        return AlluvialRestore(networks=networks, warnings=warnings)
    first = valid[0]
    raw_options = first.get("options")
    options: dict[str, Any] = {}
    if isinstance(raw_options, dict):
        for key in SAVED_OPTION_KEYS:
            if key not in raw_options:
                continue
            value = raw_options[key]
            if OPTION_RULES[key](value):
                options[key] = value
            else:
                warnings.append(f"ignoring the saved option {key} (invalid value)")
    color_scheme = None
    if "colorScheme" in first:
        scheme = first["colorScheme"]
        if isinstance(scheme, str) and scheme in SCHEMES:
            color_scheme = scheme
        else:
            warnings.append("ignoring the saved color scheme (unknown scheme)")
    color_tone = None
    if "colorTone" in first:
        tone = first["colorTone"]
        if isinstance(tone, str) and tone in TONES:
            color_tone = tone
        else:
            warnings.append("ignoring the saved color tone (unknown tone)")
    color_offset = None
    has_color_offset = False
    if "colorOffset" in first:
        offset = first["colorOffset"]
        if offset is None or _finite(offset):
            color_offset = offset
            has_color_offset = True
        else:
            warnings.append("ignoring the saved color offset (invalid value)")
    return AlluvialRestore(
        options=options,
        color_scheme=color_scheme,
        color_tone=color_tone,
        color_offset=color_offset,
        has_color_offset=has_color_offset,
        networks=networks,
        warnings=warnings,
    )


def sort_by_saved_position(files: Sequence[NetworkFile]) -> list[NetworkFile]:
    """The files in saved order when they form one complete save (TS ``sortBySavedPosition``), else unchanged."""
    valid, _ = _complete_save([_diagram_block(b) for b in _v1_blocks(files, None)])
    if valid is None:
        return list(files)
    order = sorted(range(len(files)), key=lambda i: valid[i]["position"])
    return [files[i] for i in order]
