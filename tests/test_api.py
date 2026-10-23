"""End-to-end checks of the public API: layout/draw/plot on paths, NetworkFiles and live Infomap objects."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from functools import cache
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest
from conftest import DATA_DIR, assert_matches, load_fixture
from helpers_geometry import geometry_from_fixture
from matplotlib.patches import Rectangle

import alluvial
from alluvial import AlluvialGeometry

infomap = pytest.importorskip("infomap")

ROOT = Path(__file__).resolve().parents[1]
FTREES = [DATA_DIR / f"planted_t{i}.ftree" for i in range(3)]


@cache
def _build_infomap(stem: str):
    spec = importlib.util.spec_from_file_location(
        "make_datasets", ROOT / "tools/ts-fixtures/make_datasets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_infomap(stem)


def _memory_network(seed: int) -> infomap.Infomap:
    """A small second-order network: two triangles joined by a bridge, as state nodes."""
    im = infomap.Infomap(two_level=True, seed=seed, num_trials=5, silent=True)
    names = {1: "a", 2: "b", 3: "c", 4: "d", 5: "e", 6: "f"}
    for node_id, name in names.items():
        im.set_name(node_id, name)
    # state id -> physical id
    states = {1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5, 7: 6, 8: 4}
    for state_id, node_id in states.items():
        im.add_state_node(state_id, node_id)
    links = [(1, 2), (2, 3), (3, 1), (4, 5), (5, 6), (6, 7), (7, 8), (8, 4)]
    if seed % 2:
        links.append((1, 5))
    for u, v in links:
        im.add_link(u, v)
    im.run()
    return im


def _strip_ids(value):
    if isinstance(value, dict):
        return {k: _strip_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [_strip_ids(v) for v in value]
    return value


def _artists(ax) -> tuple[int, int]:
    """Module rectangles and streamlines (a two-colour streamline is a clipped gradient image)."""
    rects = sum(isinstance(p, Rectangle) for p in ax.patches)
    return rects, len(ax.patches) - rects + len(ax.images)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def test_layout_of_infomap_state_networks_matches_ts_fixture() -> None:
    fx = load_fixture("states-tree__colored")
    ims = [_build_infomap("states_t0"), _build_infomap("states_t1")]
    geom = alluvial.layout(ims, names=fx["inputs"]["networkNames"], colors="similarity")
    expected = geometry_from_fixture(fx)
    assert [n.name for n in geom.networks] == ["states_t0.tree", "states_t1.tree"]
    res = assert_matches(
        _strip_ids(geom.to_dict()),
        _strip_ids(expected.to_dict()),
        ignore={"name_candidates", "name_highlight_indices", "name_insignificant"},
    )
    assert res.non_bitwise == 0


def test_layout_of_infomap_objects_equals_layout_of_their_files() -> None:
    ims = [_build_infomap(f"planted_t{i}") for i in range(3)]
    names = [f"planted_t{i}.tree" for i in range(3)]
    from_objects = alluvial.layout(ims, names=names)
    from_files = alluvial.layout([DATA_DIR / name for name in names])
    assert _strip_ids(from_objects.to_dict()) == _strip_ids(from_files.to_dict())
    assert [n.id for n in from_objects.networks] == ["net0", "net1", "net2"]
    assert [n.name for n in alluvial.layout(ims).networks] == ["network 0", "network 1", "network 2"]


def test_plot_infomap_objects_including_memory_network(tmp_path: Path) -> None:
    ims = [_memory_network(1), _memory_network(2)]
    nf = alluvial.read(ims[0])
    assert nf.is_state_network and len(nf.nodes) == 8
    geom = alluvial.layout(ims, names=["t0", "t1"])
    labels = [m.label.text.split("\n") for n in geom.networks for m in n.modules if m.label]
    assert labels and all(set(lines) <= set("abcdef") and len(lines) == len(set(lines)) for lines in labels)
    ax = alluvial.plot(ims, names=["t0", "t1"])
    rects, streamlines = _artists(ax)
    assert rects == sum(len(m.groups) for n in geom.networks for m in n.modules)
    assert streamlines == len(geom.streamlines) > 0
    assert {"t0", "t1"} <= {t.get_text() for t in ax.texts}
    ax.figure.savefig(tmp_path / "memory.png")
    assert (tmp_path / "memory.png").stat().st_size > 0


def test_plot_ftree_paths(tmp_path: Path) -> None:
    ax = alluvial.plot([str(p) for p in FTREES[:2]])
    geom = alluvial.layout([str(p) for p in FTREES[:2]])
    assert _artists(ax)[1] == len(geom.streamlines)
    assert {"planted_t0.ftree", "planted_t1.ftree"} <= {t.get_text() for t in ax.texts}
    for fmt in ("png", "pdf", "svg"):
        ax.figure.savefig(tmp_path / f"out.{fmt}")
        assert (tmp_path / f"out.{fmt}").stat().st_size > 0


@pytest.mark.parametrize("colors", ["similarity", "module_id", "nodes", None])
def test_layout_colors(colors) -> None:
    geom = alluvial.layout(FTREES, colors=colors)
    assert isinstance(geom, AlluvialGeometry)
    indices = {g.highlight_index for n in geom.networks for m in n.modules for g in m.groups}
    if colors is None:
        assert indices == {-1}
    else:
        assert indices - {-1}
    alluvial.draw(geom)


# Two partitions that split the nodes differently, so the colors depend on the network that sets them.
_COLOR_NETWORKS = [
    {"a": 1, "b": 1, "c": 2, "d": 2, "e": 3, "f": 3},
    {"a": 1, "b": 2, "c": 2, "d": 3, "e": 3, "f": 1},
]


def _group_indices(geom: AlluvialGeometry) -> list[list[set[int]]]:
    return [[{g.highlight_index for g in m.groups} for m in n.modules] for n in geom.networks]


def test_default_colors_are_module_id() -> None:
    assert _group_indices(alluvial.layout(FTREES)) == _group_indices(
        alluvial.layout(FTREES, colors="module_id")
    )


@pytest.mark.parametrize("ref", [1, "net1", "second"])
def test_color_network_colors_nodes_by_that_network(ref) -> None:
    geom = alluvial.layout(_COLOR_NETWORKS, names=["first", "second"], colors="nodes", color_network=ref)
    by_network = _group_indices(geom)
    # every module of the coloring network has one color, a different one per module
    colors = by_network[1]
    assert all(len(indices) == 1 for indices in colors)
    assert len(set().union(*colors)) == len(colors)
    # the modules of the other network mix them
    assert any(len(indices) > 1 for indices in by_network[0])


def test_color_network_default_is_the_first_network() -> None:
    first = _group_indices(alluvial.layout(_COLOR_NETWORKS, colors="nodes"))
    assert first == _group_indices(alluvial.layout(_COLOR_NETWORKS, colors="nodes", color_network=0))
    assert first != _group_indices(alluvial.layout(_COLOR_NETWORKS, colors="nodes", color_network=1))


def test_color_network_errors() -> None:
    with pytest.raises(ValueError, match="color_network: no network 2"):
        alluvial.layout(_COLOR_NETWORKS, colors="nodes", color_network=2)
    with pytest.raises(ValueError, match="color_network: no network 'other'"):
        alluvial.layout(_COLOR_NETWORKS, colors="nodes", color_network="other")
    with pytest.raises(ValueError, match='color_network requires colors="nodes"'):
        alluvial.layout(_COLOR_NETWORKS, color_network=1)
    with pytest.raises(ValueError, match="color_network requires"):
        alluvial.layout(_COLOR_NETWORKS, colors="similarity", color_network=1)
    with pytest.raises(ValueError, match="color_network requires"):
        alluvial.layout(_COLOR_NETWORKS, highlight={"x": ["a"]}, color_network=1)
    with pytest.raises(TypeError, match="color_network must be"):
        alluvial.layout(_COLOR_NETWORKS, colors="nodes", color_network=1.0)


def test_plot_forwards_color_network() -> None:
    ax = alluvial.plot(_COLOR_NETWORKS, colors="nodes", color_network=1)
    geom = alluvial.get_artists(ax).geometry
    assert all(len(indices) == 1 for indices in _group_indices(geom)[1])
    plt.close(ax.figure)


def test_plot_into_subplots(tmp_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    a = alluvial.plot(FTREES[:2], ax=axes[0], colors="module_id")
    b = alluvial.plot([_memory_network(1), _memory_network(3)], ax=axes[1], fontsize=6)
    assert a is axes[0] and b is axes[1]
    assert a.figure is fig and len(fig.axes) == 2
    fig.savefig(tmp_path / "subplots.png")
    assert (tmp_path / "subplots.png").stat().st_size > 0


def test_layout_does_not_import_matplotlib() -> None:
    code = f"""
import sys
import alluvial
geom = alluvial.layout({[str(p) for p in FTREES]!r}, colors="nodes")
assert geom.streamlines
bad = sorted(m for m in sys.modules if m == "matplotlib" or m.startswith("matplotlib."))
assert not bad, bad
"""
    subprocess.run([sys.executable, "-c", code], check=True)
