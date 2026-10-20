"""Build an ``AlluvialGeometry`` straight from fixture JSON, so the renderer can be developed without the engine."""

from __future__ import annotations

import math
from typing import Any

from alluvial.geometry import (
    AlluvialGeometry,
    GroupGeometry,
    Label,
    ModuleGeometry,
    NetworkGeometry,
    OutlineGeometry,
    StreamlineGeometry,
)
from alluvial.layout import LayoutOptions


def _module_label(label: dict[str, Any]) -> tuple[Label | None, tuple[str, ...]]:
    names = tuple(entry["name"] for entry in label["names"])
    if not label["shown"] or not names:
        return None, names
    pos = label["namePosition"]
    center = math.ceil(len(names) / 2) - 1
    return Label("\n".join(names), pos["x"], pos["y"], label["textAnchor"], center), names


def geometry_from_fixture(fx: dict[str, Any]) -> AlluvialGeometry:
    """The geometry ``build_geometry`` must produce for this fixture.

    Visible modules in fixture (layout) order, groups in fixture order, streamlines in the fixture's per-network
    ``links`` (draw) order, and the labels the TS renderer shows.
    """
    index_by_id = {n["networkId"]: i for i, n in enumerate(fx["networks"])}
    networks = []
    streamlines = []
    for i, n in enumerate(fx["networks"]):
        hierarchy = n["hierarchy"]
        order = {item["moduleId"]: k for k, item in enumerate(hierarchy) if item["type"] == "module"}
        outlines = tuple(
            OutlineGeometry(
                path=item["path"],
                level=item["moduleLevel"],
                max_level=item["maxModuleLevel"],
                x=item["x"],
                y=item["y"],
                width=item["width"],
                height=item["height"],
                order=k,
            )
            for k, item in enumerate(hierarchy)
            if item["type"] == "tree"
        )
        modules = []
        for m in n["modules"]:
            if not m["visible"]:
                continue
            groups = tuple(
                GroupGeometry(
                    highlight_index=g["highlightIndex"],
                    insignificant=g["insignificant"],
                    x=g["x"],
                    y=g["y"],
                    width=g["width"],
                    height=g["height"],
                    flow=g["flow"],
                )
                for g in m["groups"]
            )
            label, names = _module_label(m["label"])
            modules.append(
                ModuleGeometry(
                    id=m["moduleId"],
                    path=tuple(m["path"]),
                    network_index=i,
                    flow=m["flow"],
                    x=m["x"],
                    y=m["y"],
                    width=m["width"],
                    height=m["height"],
                    highlight_index=m["highlightIndex"],
                    groups=groups,
                    label=label,
                    largest_leaf_names=names,
                    level=m["moduleLevel"],
                    max_level=m["maxModuleLevel"],
                    order=order[m["moduleId"]],
                    name=m["label"].get("customName") or "",
                )
            )
        pos = n["namePosition"]
        networks.append(
            NetworkGeometry(
                id=n["networkId"],
                name=n["name"],
                index=n["index"],
                x=n["x"],
                y=n["y"],
                width=n["width"],
                height=n["height"],
                flow=n["flow"],
                name_label=Label(n["name"], pos["x"], pos["y"], "middle"),
                modules=tuple(modules),
                outlines=outlines,
            )
        )
        for link in n["links"]:
            left, right = link["left"], link["right"]
            streamlines.append(
                StreamlineGeometry(
                    id=link["id"],
                    left=(index_by_id[left["networkId"]], left["moduleId"], left["groupHighlightIndex"]),
                    right=(index_by_id[right["networkId"]], right["moduleId"], right["groupHighlightIndex"]),
                    x0=link["x0"],
                    y0=link["y0"],
                    h0=link["h0"],
                    x1=link["x1"],
                    y1=link["y1"],
                    h1=link["h1"],
                    avg_height=link["avgHeight"],
                    highlight_index=link["highlightIndex"],
                    left_highlight_index=link["leftHighlightIndex"],
                    right_highlight_index=link["rightHighlightIndex"],
                    left_insignificant=left["groupInsignificant"],
                    right_insignificant=right["groupInsignificant"],
                )
            )
    d = fx["diagram"]
    return AlluvialGeometry(
        width=d["width"],
        height=d["height"],
        networks=tuple(networks),
        streamlines=tuple(streamlines),
        palette=tuple(fx["highlightColors"]),
        options=LayoutOptions.from_ts(fx["inputs"]["options"]),
    )
