"""Headless (Agg) tests of the matplotlib renderer, driven by geometry built straight from the TS fixtures."""

from __future__ import annotations

import itertools
import sys
import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest
from conftest import load_fixture
from helpers_geometry import geometry_from_fixture
from matplotlib.colors import to_rgb
from matplotlib.patches import Rectangle

import alluvial
from alluvial import mpl as amp
from alluvial._palette import DEFAULT_HIGHLIGHT_COLOR, brighter, to_rgb01


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _geom(name: str):
    return geometry_from_fixture(load_fixture(name))


def _rects(ax):
    return [p for p in ax.patches if isinstance(p, Rectangle)]


def test_artist_counts(scenario):
    geom = _geom(scenario)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        ax = alluvial.draw(geom)
    n_groups = sum(len(m.groups) for n in geom.networks for m in n.modules)
    n_streamlines = len(geom.streamlines)
    n_outlines = sum(len(n.outlines) for n in geom.networks)
    art = alluvial.get_artists(ax)
    assert len(art.outlines) == n_outlines  # shadows (Rectangles) by default
    assert len(_rects(ax)) == n_groups + n_outlines
    assert len(ax.patches) - n_groups - n_outlines + len(ax.images) == n_streamlines
    n_label_lines = sum(
        len(m.label.text.split("\n")) for n in geom.networks for m in n.modules if m.label is not None
    )
    n_names = sum(1 for n in geom.networks if n.name_label.text)
    assert len(ax.texts) == n_label_lines + n_names
    assert not ax.axison


def test_gradient_off_draws_only_patches():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom, gradient=False)
    assert not ax.images
    assert len(ax.patches) == sum(len(m.groups) for n in geom.networks for m in n.modules) + len(
        geom.streamlines
    )


def test_ax_reuse_in_subplots():
    fig, axs = plt.subplots(1, 2, figsize=(8, 4))
    left = alluvial.draw(_geom("planted-ftree__colored"), axs[0])
    right = alluvial.draw(_geom("states-tree__default"), axs[1], fontsize=6)
    assert left is axs[0] and right is axs[1]
    assert len(fig.axes) == 2
    assert left.texts and right.texts
    fig.canvas.draw()


@pytest.mark.parametrize("fmt", ["png", "pdf", "svg"])
def test_savefig_formats(tmp_path, fmt):
    ax = alluvial.draw(_geom("planted-ftree__colored"))
    out = tmp_path / f"diagram.{fmt}"
    ax.figure.savefig(out)
    assert out.stat().st_size > 1000


def test_own_figure_is_sized_by_content():
    geom = _geom("states-tree__default")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ax = alluvial.draw(geom)
    width_in, height_in = ax.figure.get_size_inches()
    n_modules = max(len(n.modules) for n in geom.networks)
    lo, hi = amp.FIG_HEIGHT_RANGE
    expected = min(max(amp.FIG_HEIGHT_BASE + amp.FIG_HEIGHT_PER_MODULE * n_modules, lo), hi)
    assert height_in == pytest.approx(expected)
    assert height_in < geom.height / 72  # not one point per layout px
    diagram = amp.FIG_WIDTH_BASE + amp.FIG_WIDTH_PER_NETWORK * (len(geom.networks) - 1)
    assert diagram < width_in <= 2 * amp.FIG_DIAGRAM_MAX_WIDTH
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    assert x0 < 0 < geom.width < x1 and y0 < 0 < geom.height <= y1
    # Text sizes stay in points: the module labels keep the default size.
    assert alluvial.get_artists(ax).module_labels[0].get_fontsize() == pytest.approx(
        amp._fontsize_pt(None, "small")
    )


def _fake_geometry(modules_per_network, width=800.0):
    from types import SimpleNamespace

    networks = [
        SimpleNamespace(modules=[None] * k, x=240.0 * i, width=80.0)
        for i, k in enumerate(modules_per_network)
    ]
    return SimpleNamespace(networks=networks, width=width, height=600.0)


def test_own_figure_height_grows_with_modules_within_bounds():
    heights = [amp._figure_height(_fake_geometry([k, 1])) for k in range(0, 200)]
    assert all(a <= b for a, b in itertools.pairwise(heights))
    assert min(heights) == pytest.approx(amp.FIG_HEIGHT_RANGE[0])
    assert max(heights) == pytest.approx(amp.FIG_HEIGHT_RANGE[1])
    assert heights[10] > heights[4]  # grows inside the range
    # The fullest network counts, not the total.
    assert amp._figure_height(_fake_geometry([10, 2])) == amp._figure_height(_fake_geometry([2, 10, 3]))


def test_own_figure_width_grows_with_networks_and_labels():
    widths = [amp._figure_width(_fake_geometry([3] * n), 0.0) for n in range(1, 8)]
    assert all(a < b for a, b in itertools.pairwise(widths))
    geom = _fake_geometry([3, 3])
    assert amp._figure_width(geom, 72.0) == pytest.approx(amp._figure_width(geom, 0.0) + 1.0)
    # Label space is capped at the diagram width; long network names widen the diagram.
    assert amp._figure_width(geom, 1e6) == pytest.approx(2 * amp._figure_width(geom, 0.0))
    assert amp._figure_width(geom, 0.0, name_pt=400.0) > amp._figure_width(geom, 0.0) + 400.0 / 72


def test_user_axes_and_figsize_are_kept():
    geom = _geom("states-tree__default")
    fig, ax = plt.subplots(figsize=(3.4, 2.4))
    assert alluvial.draw(geom, ax) is ax
    fig.canvas.draw()
    assert tuple(fig.get_size_inches()) == pytest.approx((3.4, 2.4))


def test_y_orientation_largest_module_at_bottom():
    geom = _geom("states-tree__default")
    ax = alluvial.draw(geom, module_labels=False, network_labels=False)
    first = geom.networks[0]
    largest = max(first.modules, key=lambda m: m.flow)
    rects = [r for r in _rects(ax) if r.get_x() == first.x]
    bottom = min(rects, key=lambda r: r.get_y())
    assert bottom.get_y() == pytest.approx(geom.height - largest.y - largest.height)
    assert bottom.get_y() == pytest.approx(0.0, abs=1e-6)
    assert max(r.get_y() + r.get_height() for r in rects) <= geom.height + 1e-9


def _visible(texts):
    return [t for t in texts if t.get_visible()]


def test_labels_only_on_first_and_last_network():
    geom = _geom("planted-ftree__colored")
    assert len(geom.networks) == 3
    ax = alluvial.draw(geom, network_labels=False)
    ax.figure.canvas.draw()
    first, last = geom.networks[0], geom.networks[-1]
    left_edge = ax.transData.transform((first.x, 0))[0]
    right_edge = ax.transData.transform((last.x + last.width, 0))[0]
    texts = _visible(ax.texts)
    assert texts
    for t in texts:
        box = t.get_window_extent()
        assert box.x1 <= left_edge or box.x0 >= right_edge, t.get_text()
        assert t.get_ha() == ("right" if box.x1 <= left_edge else "left")
    assert {t.get_ha() for t in texts} == {"left", "right"}


def test_network_names_below_diagram():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom, module_labels=False)
    ax.figure.canvas.draw()
    assert [t.get_text() for t in ax.texts] == [n.name for n in geom.networks]
    bottom = ax.transData.transform((0, 0))[1]
    assert all(t.get_window_extent().y1 <= bottom for t in ax.texts)


def test_max_label_lines():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom, max_label_lines=1, network_labels=False)
    labelled = [m for n in geom.networks for m in n.modules if m.label is not None]
    assert len(ax.texts) == len(labelled)
    assert {t.get_text() for t in _visible(ax.texts)} <= {m.largest_leaf_names[0] for m in labelled}
    with pytest.raises(ValueError, match="max_label_lines"):
        alluvial.draw(geom, max_label_lines=-1)
    with pytest.raises(TypeError, match="max_label_lines"):
        alluvial.draw(geom, max_label_lines=2.5)
    np = pytest.importorskip("numpy")
    assert len(alluvial.draw(geom, max_label_lines=np.int64(1), network_labels=False).texts) == len(labelled)


def _texts_inside_axes(ax):
    ax.figure.canvas.draw()
    renderer = ax.figure.canvas.get_renderer()
    box = ax.get_window_extent(renderer)
    for t in _visible(ax.texts):
        tb = t.get_window_extent(renderer)
        assert tb.x0 >= box.x0 - 0.5 and tb.x1 <= box.x1 + 0.5, t.get_text()
        assert tb.y0 >= box.y0 - 0.5 and tb.y1 <= box.y1 + 0.5, t.get_text()


def test_limits_cover_labels_own_figure():
    _texts_inside_axes(alluvial.draw(_geom("science-stree__nameColored")))


def test_limits_cover_labels_given_axes():
    _fig, axs = plt.subplots(1, 2, figsize=(9, 4))
    alluvial.draw(_geom("planted-ftree__colored"), axs[0])
    alluvial.draw(_geom("science-stree__nameColored"), axs[1])
    _texts_inside_axes(axs[0])
    _texts_inside_axes(axs[1])


def test_default_and_insignificant_colors():
    geom = _geom("states-tree__default")
    ax = alluvial.draw(geom)
    groups = [g for n in geom.networks for m in n.modules for g in m.groups]
    for g, r in zip(groups, _rects(ax), strict=True):
        expected = brighter(DEFAULT_HIGHLIGHT_COLOR) if g.insignificant else DEFAULT_HIGHLIGHT_COLOR
        assert r.get_facecolor()[:3] == pytest.approx(to_rgb01(expected))


def test_palette_colors_used():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom)
    groups = [g for n in geom.networks for m in n.modules for g in m.groups]
    for g, r in zip(groups, _rects(ax), strict=True):
        if g.highlight_index >= 0 and not g.insignificant:
            assert r.get_facecolor()[:3] == pytest.approx(to_rgb01(geom.palette[g.highlight_index]))


def test_palette_cycling_warns():
    geom = _geom("planted-ftree__colored")
    assert len(geom.palette) > 2
    with pytest.warns(UserWarning, match="cycling"):
        ax = alluvial.draw(geom, palette=["red", "blue"])
    groups = [g for n in geom.networks for m in n.modules for g in m.groups]
    for g, r in zip(groups, _rects(ax), strict=True):
        if g.highlight_index == 2 and not g.insignificant:
            assert r.get_facecolor()[:3] == pytest.approx(to_rgb("red"))


def test_palette_colormap_name():
    geom = _geom("planted-ftree__colored")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        alluvial.draw(geom, palette="viridis")
        alluvial.draw(geom, palette="tab10")
    with pytest.raises(ValueError, match="colormap"):
        alluvial.draw(geom, palette="not-a-colormap")


def test_streamline_gradient_stops():
    left, right = (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    strip = amp._gradient(left, right)[0]
    t = np.linspace(0, 1, len(strip))
    assert np.allclose(strip[t <= 0.15], left)
    assert np.allclose(strip[t >= 0.85], right)
    mid = strip[np.argmin(abs(t - 0.5))]
    assert mid[0] == pytest.approx(0.5, abs=0.01) and mid[2] == pytest.approx(0.5, abs=0.01)


def test_respects_rcparams():
    with plt.rc_context({"text.color": "tab:green", "font.size": 12}):
        ax = alluvial.draw(_geom("states-tree__default"))
    assert {t.get_color() for t in ax.texts} == {"tab:green"}
    art = alluvial.get_artists(ax)
    assert [t.get_fontsize() for t in art.module_labels] == pytest.approx(
        [10.0] * len(art.module_labels), rel=1e-3
    )  # "small"
    assert {t.get_fontsize() for t in art.network_labels} == {12.0}


def test_plot_splits_kwargs(monkeypatch):
    geom = _geom("states-tree__default")
    seen = {}

    def fake_layout(networks, **kwargs):
        seen["networks"], seen["kwargs"] = networks, kwargs
        return geom

    monkeypatch.setattr(sys.modules["alluvial.layout"], "layout", fake_layout)
    _fig, ax = plt.subplots()
    out = alluvial.plot(["a.tree", "b.tree"], ax, height=400, colors=None, fontsize=6, palette="tab10")
    assert out is ax
    assert seen["networks"] == ["a.tree", "b.tree"]
    assert seen["kwargs"] == {"height": 400, "colors": None}


def test_undefined_palette_entry_is_drawn_black():
    """The store's highlightColors can hold JS ``undefined`` (None); TS fills it black instead of failing."""
    import dataclasses

    geom = _geom("planted-ftree__colored")
    geom = dataclasses.replace(geom, palette=(None, *geom.palette[1:]))
    ax = alluvial.draw(geom)
    black = [r for r in alluvial.get_artists(ax).modules if r.get_facecolor()[:3] == (0.0, 0.0, 0.0)]
    assert any(
        g.highlight_index == 0 and not g.insignificant
        for n in geom.networks
        for m in n.modules
        for g in m.groups
    )
    assert black


def test_measure_cache_is_keyed_by_font_and_renderer() -> None:
    """``_measure`` memoizes metrics; a change of font size, family or renderer scale must not hit a stale entry."""
    from matplotlib.text import Text

    fig = plt.figure(dpi=100)
    renderer = fig.canvas.get_renderer()
    small, large = Text(text="", fontsize=8), Text(text="", fontsize=16)
    w8 = amp._measure(small, "Some label", renderer)[0]
    w16 = amp._measure(large, "Some label", renderer)[0]
    assert w16 > 1.5 * w8
    small.set_fontsize(16)  # same Text object, mutated font
    assert amp._measure(small, "Some label", renderer)[0] == w16
    fig2 = plt.figure(dpi=300)
    w300 = amp._measure(large, "Some label", fig2.canvas.get_renderer())[0]
    uncached = fig2.canvas.get_renderer().get_text_width_height_descent(
        "Some label", large.get_fontproperties(), ismath=False
    )[0] / fig2.canvas.get_renderer().points_to_pixels(1.0)
    assert w300 == uncached
