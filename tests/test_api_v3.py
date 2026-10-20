"""Public v3 API: web-app files (``save_diagram``, ``read``), the 2019 format's rejection, input colours and named
schemes."""

from __future__ import annotations

import json
import warnings
import zipfile
from pathlib import Path
from typing import Any

import pytest
from conftest import DATA_DIR, FIXTURES_DIR

import alluvial
from alluvial.io import read

MULTILEVEL = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
PLANTED_JSON = [DATA_DIR / f"planted_t{i}.json" for i in range(3)]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / "v3" / f"{name}.json").read_text(encoding="utf-8"))


#: A 2019 saved diagram (as the web app saved diagrams before 2022): top-level ``networks``, no ``nodes``.
SAVED_2019 = {
    "version": "0.3.0",
    "timestamp": 0,
    "state": {"height": 600},
    "networks": [{"id": "a", "name": "a", "moduleNames": [], "nodes": [{"path": "1:1", "flow": 1, "id": 1}]}],
}
NO_2019 = r"the 2019 saved-diagram format is no longer supported; use alluvial 0\.4 to convert"


def test_read_rejects_the_2019_saved_diagram(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=NO_2019):
        read(SAVED_2019)
    path = tmp_path / "diagram.json"
    path.write_text(json.dumps(SAVED_2019), encoding="utf-8")
    with pytest.raises(ValueError, match="diagram.json: " + NO_2019):
        read(path)
    with pytest.raises(ValueError, match=NO_2019):
        alluvial.layout([path])
    archive = tmp_path / "diagram.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("diagram.json", json.dumps(SAVED_2019))
    with pytest.raises(ValueError, match="diagram.zip: diagram.json: " + NO_2019):
        read(archive)


def assert_same_diagram(a: Any, b: Any, tol: float = 1e-9) -> None:
    """Reload vs original: the same palette, options and modules (ids, names, colours) in the same order, and the
    same geometry up to float summation order (the reload's network ids are the file names)."""
    assert a.palette == b.palette
    assert a.options == b.options
    assert (a.width, a.height) == (b.width, b.height)
    for na, nb in zip(a.networks, b.networks, strict=True):
        assert na.name == nb.name
        assert [(m.id, m.name, m.highlight_index) for m in na.modules] == [
            (m.id, m.name, m.highlight_index) for m in nb.modules
        ]
        for ma, mb in zip(na.modules, nb.modules, strict=True):
            assert abs(ma.y - mb.y) <= tol and abs(ma.height - mb.height) <= tol
    assert len(a.streamlines) == len(b.streamlines)


def test_save_diagram(tmp_path: Path) -> None:
    kwargs = {"module_level": 2, "scheme": "Set1"}
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # nothing is lost any more
        loose = alluvial.save_diagram(MULTILEVEL, tmp_path / "web", loose=True, height=300, **kwargs)
        out = alluvial.save_diagram(MULTILEVEL, tmp_path / "web.zip", height=300, **kwargs)
        default = alluvial.save_diagram(MULTILEVEL, tmp_path / "diagram", height=300, **kwargs)
    names = [f"0{i}_multilevel_t{i}.tree.json" for i in range(3)]
    assert loose == tmp_path / "web"
    assert sorted(p.name for p in loose.iterdir()) == names
    assert default == tmp_path / "diagram.zip"  # a zip by default
    for zipped in (out, default):
        with zipfile.ZipFile(zipped) as zf:
            assert zf.namelist() == names
    original = alluvial.layout(MULTILEVEL, height=300, **kwargs)
    # a directory, a zip and read() of the files in any order restore the diagram, options included
    for source in ([loose], [out], read(list(reversed(sorted(loose.iterdir()))))):
        assert_same_diagram(alluvial.layout(source), original)
    # explicit keywords win over the stored options
    assert alluvial.layout([out], height=500).height == 500
    # the 2019 format's keywords are gone
    for removed in ({"format": "diagram"}, {"version": "0.3.0"}, {"timestamp": 0}):
        with pytest.raises(TypeError, match="unexpected keyword"):
            alluvial.save_diagram(MULTILEVEL, tmp_path / "x", **removed)
    # one .json file only for one network
    single = alluvial.save_diagram(MULTILEVEL[:1], tmp_path / "one.json")
    assert_same_diagram(alluvial.layout([single]), alluvial.layout(MULTILEVEL[:1]))
    with pytest.raises(ValueError, match="only for a diagram of one network"):
        alluvial.save_diagram(MULTILEVEL, tmp_path / "all.json")


def test_save_converts_matplotlib_colours(tmp_path: Path) -> None:
    pytest.importorskip("matplotlib")
    path = alluvial.save_diagram(
        MULTILEVEL, tmp_path / "web", loose=True, highlight={"a": ["1", "2"]}, highlight_colors=["tab:blue"]
    )
    for file in path.glob("*.json"):
        assert json.loads(file.read_text(encoding="utf-8"))["colors"] == ["#1f77b4"]


def test_json_colors_are_kept() -> None:
    a = alluvial.layout([DATA_DIR / "jscolors_a.json"])
    assert a.palette == ("#f00", "#0f0")
    assert alluvial.layout([DATA_DIR / "jscolors_a.json"], colors="similarity").palette != a.palette
    b = read(DATA_DIR / "jscolors_b.json")
    before = [n.highlight_index for n in b.nodes]
    geom = alluvial.layout([b])
    assert geom.palette == ("#0f0", "#00f")
    assert [n.highlight_index for n in b.nodes] == before  # the caller's nodes are not mutated


def test_schemes() -> None:
    fx = _fixture("multilevel-tree__schemePaired")
    assert list(alluvial.layout(MULTILEVEL, scheme="Paired").palette) == fx["highlightColors"]
    assert alluvial.layout(MULTILEVEL, scheme=["#000000", "#ffffff"]).palette[0] == "#000000"
    with pytest.raises(ValueError, match="did you mean 'Paired'"):
        alluvial.layout(MULTILEVEL, scheme="paired")
    with pytest.raises(TypeError, match="scheme"):
        alluvial.layout(MULTILEVEL, scheme=3)
    labels = alluvial.layout(MULTILEVEL, highlight={"a": ["1"]}, scheme="Set1").highlight_labels
    assert labels[0].color == alluvial.palette.SCHEMES["Set1"][0]


def test_draw_shows_module_names() -> None:
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = {(0, "1"): "Physical sciences", (1, "1"): "Hidden in the middle", (2, "1"): "Physical sciences"}
    ax = alluvial.plot(MULTILEVEL, module_names=names)
    texts = [t.get_text() for t in alluvial.get_artists(ax).module_labels]
    assert texts.count("Physical sciences") == 2  # labels on the first and last network only
    assert "Hidden in the middle" not in texts
    plt.close(ax.figure)


def test_warnings_point_at_the_caller() -> None:
    pytest.importorskip("matplotlib")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with pytest.warns(UserWarning, match="module_level is deeper") as record:
        alluvial.layout(MULTILEVEL, module_level=3)
    assert {Path(w.filename).name for w in record} == {"test_api_v3.py"}
    with pytest.warns(UserWarning, match="module_level is deeper") as record:
        ax = alluvial.plot(MULTILEVEL, module_level=3)
    assert {Path(w.filename).name for w in record} == {"test_api_v3.py"}
    plt.close(ax.figure)
    with pytest.warns(UserWarning, match="shared by several nodes") as record:
        read(DATA_DIR / "dupname_t1.tree", identifier="name")
    assert {Path(w.filename).name for w in record} == {"test_api_v3.py"}


def test_empty_diagram_warns() -> None:
    networks = [json.loads(path.read_text(encoding="utf-8")) for path in PLANTED_JSON]
    for network in networks:
        for node in network["nodes"]:
            node["flow"] = 0
    with pytest.warns(UserWarning, match="diagram is empty"):
        geom = alluvial.layout(networks)
    assert len(geom.networks) == 3


def test_save_diagram_rejects_a_geometry(tmp_path: Path) -> None:
    geom = alluvial.layout(MULTILEVEL)
    with pytest.raises(TypeError, match=r"pass the networks and the same keywords to alluvial\.save_diagram"):
        alluvial.save_diagram(geom, tmp_path / "web")


def test_save_diagram_rejects_a_json_path(tmp_path: Path) -> None:
    # A .json path holds the one file of a single-network diagram only (it once made a directory called web.json).
    with pytest.raises(ValueError, match=r"only for a diagram of one network"):
        alluvial.save_diagram(MULTILEVEL, tmp_path / "web.JSON")
    assert list(tmp_path.iterdir()) == []
    with zipfile.ZipFile(alluvial.save_diagram(MULTILEVEL, tmp_path / "d.ZIP")) as zf:
        assert len(zf.namelist()) == len(MULTILEVEL)


def test_read_points_web_app_files_to_their_json(tmp_path: Path) -> None:
    out = alluvial.save_diagram(MULTILEVEL, tmp_path / "web.zip")
    zipped = read(out)  # v4: a zip reads as one NetworkFile per file (test_v4_fixtures)
    assert isinstance(zipped, list) and len(zipped) == len(MULTILEVEL)
    with pytest.raises(ValueError, match=r"zip archive of network files; read it with alluvial.read"):
        alluvial.io.read_file(out)
    folder = alluvial.save_diagram(MULTILEVEL, tmp_path / "web", loose=True)
    assert [nf.id for nf in read(folder)] == [nf.id for nf in zipped]  # a directory reads like the zip
    geom = alluvial.layout(sorted(folder.glob("*.json")))
    assert [n.name for n in geom.networks] == [p.name for p in MULTILEVEL]
    assert alluvial.layout(zipped) == geom


def test_number_paths_are_top_level_modules() -> None:
    """TS ``setIdentifiers(nodes, "json")`` turns any non-array path into ``TreePath.toArray(path)``: a number path
    ``2`` is ``[2]`` (verified against TS)."""
    from alluvial.io.json_reader import from_json_dict

    nodes = [{"path": p, "flow": 0.25, "id": i, "name": f"n{i}"} for i, p in enumerate([1, "1", 2, [2]])]
    nf = from_json_dict({"nodes": nodes}, id="a", name="a")
    assert [n.path for n in nf.nodes] == [[1], [1], [2], [2]]
    with pytest.raises(ValueError, match="must be a list, a string or a number"):
        from_json_dict({"nodes": [{"path": True, "flow": 1, "id": 1}]}, id="a", name="a")
