"""Splitting a multilayer network into one ``NetworkFile`` per layer, as the web app's "split layers" does."""

# Port of expandMultilayerFile (parsers/multilayer-utils.ts). Spec: docs/dev/port-notes/v2-io.md §2 and §7.
# mergeMultilayerFiles (the UI's undo) is deliberately not ported.

from __future__ import annotations

import dataclasses
from typing import Any

from .._jscompat import is_array_index_key, js_num_str
from .identifiers import calc_statistics, set_identifiers
from .types import NetworkFile

__all__ = ["split_layers"]

DEFAULT_ID_FORMAT = "{id}_layer{layer}"


def _js_key(value: Any) -> str:
    """JS ``String(value)`` as an object property key (``undefined`` for ``None``)."""
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return js_num_str(value)
    return str(value)


def _strict_eq(a: Any, b: Any) -> bool:
    """JS ``===`` on JSON values (no bool/number/string cross-matching)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def _layer_name(layers: Any, layer_id: Any) -> Any:
    # file.layers?.find((l) => l.id === layerId)?.name ?? `Layer ${layerId}`
    if layers is not None:
        if not isinstance(layers, list):
            raise ValueError(f"`layers` must be a list of {{id, name}} objects, got {type(layers).__name__}")
        for entry in layers:
            if entry is None:  # TS: `l.id` on null throws (only when find reaches it)
                raise ValueError("`layers` has a null entry; each entry must be an {id, name} object")
            if isinstance(entry, dict) and _strict_eq(entry.get("id"), layer_id):
                name = entry.get("name")
                if name is not None:
                    return name
                break
    return f"Layer {_js_key(layer_id)}"


def split_layers(nf: NetworkFile, *, id_format: str = DEFAULT_ID_FORMAT) -> list[NetworkFile]:
    """Split a multilayer state network into one network per layer, like the web app's "split layers".

    Nodes are matched across the layers by **physical node id** (as the web app does),
    whatever identifiers ``nf`` was read with. Streamlines then connect the same physical node in adjacent layers.

    Parameters
    ----------
    nf : NetworkFile
        A multilayer network read at the state level (its first node has a ``layer_id``). Not mutated: the layers
        get copies of the nodes.
    id_format : str, default ``"{id}_layer{layer}"``
        Network id of each layer, formatted with ``id`` (``nf.id``) and ``layer`` (the layer id as a
        string, e.g. ``"3"``). The result must not contain ``"--"``.

    Returns
    -------
    list of NetworkFile
        In layer id order: non-negative integer ids ascending, then any other ids in first-seen order (only hand-made input has those). Each layer copies every field of ``nf`` (header,
        ``modules`` …) and sets ``id``, ``name`` (``nf.layers`` entry with a strictly equal ``id``, else
        ``"Layer <id>"``), ``nodes`` (file order), ``layer_id``, ``original_id = nf.id``, the statistics of its
        nodes and ``is_expanded = True``.

    Raises
    ------
    ValueError
        If ``nf`` is not multilayer.

    Notes
    -----
    Nodes without a ``layer_id`` form a last ``"Layer undefined"`` network, as in the web app. A JSON
    ``layerId: null`` reads as missing (the web app would make a ``"Layer null"`` network).

    Examples
    --------
    A multilayer state network with two layers, as Infomap JSON:

    >>> import alluvial
    >>> nf = alluvial.read(
    ...     {
    ...         "nodes": [
    ...             {"id": 1, "stateId": 1, "layerId": 1, "name": "a", "path": [1, 1], "flow": 0.25},
    ...             {"id": 2, "stateId": 2, "layerId": 1, "name": "b", "path": [1, 2], "flow": 0.25},
    ...             {"id": 1, "stateId": 3, "layerId": 2, "name": "a", "path": [1, 1], "flow": 0.25},
    ...             {"id": 2, "stateId": 4, "layerId": 2, "name": "b", "path": [2, 1], "flow": 0.25},
    ...         ]
    ...     },
    ...     network_id="net",
    ... )
    >>> layers = alluvial.split_layers(nf)
    >>> [(layer.id, layer.name) for layer in layers]
    [('net_layer1', 'Layer 1'), ('net_layer2', 'Layer 2')]
    >>> [len(network.modules) for network in alluvial.layout(layers).networks]
    [1, 2]
    """
    if not nf.is_multilayer:
        raise ValueError(
            f"network {nf.name!r} is not multilayer (its first node has no layer id), so it cannot be split into "
            "layers. Read the state level of a multilayer network: `infomap ... -o states` / "
            "im.write_tree(path, states=True), or alluvial.read(im, states=True)"
        )
    nodes = [dataclasses.replace(n) for n in nf.nodes]
    set_identifiers(nodes, "multilayer-expanded")
    groups: dict[str, tuple[Any, Any, list]] = {}  # JS key -> (first layer_id, name, nodes)
    for n in nodes:
        key = _js_key(n.layer_id)
        if key not in groups:
            groups[key] = (n.layer_id, _layer_name(nf.layers, n.layer_id), [])
        groups[key][2].append(n)
    order = sorted((k for k in groups if is_array_index_key(k)), key=int)
    order += [k for k in groups if not is_array_index_key(k)]
    out: list[NetworkFile] = []
    for key in order:
        layer_id, name, layer_nodes = groups[key]
        layer = dataclasses.replace(
            nf,
            id=id_format.format(id=nf.id, layer=key),
            name=name,
            nodes=layer_nodes,
            layer_id=layer_id,
            original_id=nf.id,
        )
        for field, value in calc_statistics(layer_nodes).items():
            setattr(layer, field, value)
        layer.is_expanded = True
        out.append(layer)
    return out
