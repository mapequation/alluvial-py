"""Agg tests of the renderer at paper sizes: label fitting, point-based text, vector output, styling, artists."""

from __future__ import annotations

import re
import warnings

import matplotlib

matplotlib.use("Agg")

import itertools
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from conftest import load_fixture
from helpers_geometry import geometry_from_fixture
from matplotlib.colors import to_rgb, to_rgba
from matplotlib.image import AxesImage
from matplotlib.patches import PathPatch, Rectangle

import alluvial
from alluvial import mpl as amp

SINGLE_COLUMN = (3.4, 2.4)
DOUBLE_COLUMN = (7.0, 2.8)
SIZES = [SINGLE_COLUMN, DOUBLE_COLUMN, (2.0, 4.5), (7.0, 1.6)]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _geom(name: str = "science-stree__nameColored"):
    return geometry_from_fixture(load_fixture(name))


def _visible(texts):
    return [t for t in texts if t.get_visible()]


def _draw_in(size, geom=None, layout=None, **kw):
    fig, ax = plt.subplots(figsize=size, layout=layout)
    alluvial.draw(_geom() if geom is None else geom, ax, **kw)
    fig.canvas.draw()
    return fig, ax


def _assert_texts_inside(ax):
    box = ax.get_window_extent()
    fig_box = ax.figure.bbox
    for t in _visible(ax.texts):
        tb = t.get_window_extent()
        for outer in (box, fig_box):
            assert outer.x0 - 0.5 <= tb.x0 and tb.x1 <= outer.x1 + 0.5, t.get_text()
            assert outer.y0 - 0.5 <= tb.y0 and tb.y1 <= outer.y1 + 0.5, t.get_text()


def _diagram_box(ax, geom):
    (x0, y0), (x1, y1) = ax.transData.transform([(0, 0), (geom.width, geom.height)])
    return x0, x1, y0, y1


# ---------------------------------------------------------------------------------------- fitting at paper sizes


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize(
    "name", ["science-stree__nameColored", "planted-ftree__colored", "states-tree__default"]
)
def test_labels_fit_inside_axes_at_paper_sizes(size, name):
    geom = _geom(name)
    _fig, ax = _draw_in(size, geom)
    _assert_texts_inside(ax)
    # The diagram keeps a usable share of the axes (it used to collapse to a sliver at single-column width).
    x0, x1, y0, y1 = _diagram_box(ax, geom)
    box = ax.get_window_extent()
    assert (x1 - x0) / box.width > 0.3
    assert (y1 - y0) / box.height > 0.5


def test_constrained_layout_refits_at_draw_time(tmp_path):
    geom = _geom()
    fig, ax = plt.subplots(figsize=SINGLE_COLUMN, layout="constrained")
    alluvial.draw(geom, ax)
    before = ax.get_window_extent().width
    fig.savefig(tmp_path / "c.png", dpi=200)
    fig.canvas.draw()
    assert ax.get_window_extent().width > before  # constrained layout grew the axes after draw() returned
    _assert_texts_inside(ax)
    x0, x1, _, _ = _diagram_box(ax, geom)
    assert (x1 - x0) / ax.get_window_extent().width > 0.4


def test_resizing_own_figure_refits():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom)
    ax.figure.set_size_inches(*SINGLE_COLUMN)
    ax.figure.canvas.draw()
    _assert_texts_inside(ax)


def test_refit_is_stable():
    fig, ax = _draw_in(SINGLE_COLUMN, layout="constrained")
    limits = (*ax.get_xlim(), *ax.get_ylim())
    texts = [(t.get_text(), t.get_visible()) for t in ax.texts]
    fig.canvas.draw()
    fig.canvas.draw()
    assert (*ax.get_xlim(), *ax.get_ylim()) == pytest.approx(limits)
    assert [(t.get_text(), t.get_visible()) for t in ax.texts] == texts
    assert not ax.stale


def test_bbox_inches_tight_keeps_labels(tmp_path):
    fig, ax = plt.subplots(figsize=DOUBLE_COLUMN)
    alluvial.draw(_geom(), ax)
    fig.savefig(tmp_path / "t.png", dpi=100, bbox_inches="tight")
    img = plt.imread(tmp_path / "t.png")
    # The axes (which holds every label) is kept whole: the crop is at least the axes size.
    box = ax.get_window_extent()
    assert img.shape[1] >= box.width * 100 / fig.dpi - 2


def test_axes_aspect_does_not_distort_text():
    geom = _geom("planted-ftree__colored")
    for size in [(7.0, 1.6), (2.0, 4.5)]:
        fig, ax = _draw_in(size, geom, network_fontsize=7)
        t = _visible(alluvial.get_artists(ax).network_labels)[0]
        assert t.get_fontsize() == 7
        # The same string as plain figure text: any data-aspect scaling would change the extent.
        # (Compare like with like; text bbox heights depend on the glyphs on matplotlib < 3.11.)
        ref = fig.text(0, 0, t.get_text(), fontproperties=t.get_fontproperties())
        got, want = t.get_window_extent(), ref.get_window_extent()
        assert (got.width, got.height) == pytest.approx((want.width, want.height))


def test_tiny_axes_warns():
    _fig, ax = plt.subplots(figsize=(0.8, 0.8))
    with pytest.warns(UserWarning, match="no room"):
        alluvial.draw(_geom(), ax, max_label_width=None)


# ------------------------------------------------------------------------------------------ geometry invariance


DRAW_OPTIONS = [
    {},
    {"fontsize": 5, "network_fontsize": 6},
    {"fontsize": 14, "max_label_lines": 1, "max_label_width": 20},
    {"palette": "tab10", "gradient": False, "streamline_alpha": 0.5},
    {"avoid_label_overlap": False, "label_pad": 10, "module_labels": False},
    {"linewidth": 0, "rasterized": True, "text_kw": {"family": "serif"}},
]


@pytest.mark.parametrize("size", [None, SINGLE_COLUMN, DOUBLE_COLUMN])
@pytest.mark.parametrize("options", DRAW_OPTIONS)
def test_layout_px_geometry_unchanged_by_draw_options(size, options):
    geom = _geom()
    before = geom.to_dict()
    if size is None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            ax = alluvial.draw(geom, **options)
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            _fig, ax = _draw_in(size, geom, **options)
    assert geom.to_dict() == before
    groups = [g for n in geom.networks for m in n.modules for g in m.groups]
    rects = alluvial.get_artists(ax).modules
    assert len(rects) == len(groups)
    for g, r in zip(groups, rects, strict=True):
        assert (r.get_x(), r.get_y(), r.get_width(), r.get_height()) == (
            g.x,
            geom.height - g.y - g.height,
            g.width,
            g.height,
        )
    lines = alluvial.get_artists(ax).streamlines
    for s, artist in zip(geom.streamlines, lines, strict=True):
        if isinstance(artist, AxesImage):
            x0, x1, _, _ = artist.get_extent()
            assert (x0, x1) == (s.x0, s.x1)
            path = artist.get_clip_path()._path  # TransformedPath
        else:
            path = artist.get_path()
        expected = [(x, geom.height - y) for _, (x, y) in s.path()]
        assert np.allclose(path.vertices, expected)


# ---------------------------------------------------------------------------------------------------- labels


def _blocks(ax):
    """Visible label lines per side as (y0, y1) display intervals, grouped by module (gid)."""
    by_module = {}
    for t in _visible(alluvial.get_artists(ax).module_labels):
        key = t.get_gid().rsplit(":", 1)[0]
        by_module.setdefault((t.get_ha(), key), []).append(t.get_window_extent())
    out = {"left": [], "right": []}
    for (ha, _), boxes in by_module.items():
        out[ha].append((min(b.y0 for b in boxes), max(b.y1 for b in boxes)))
    return out


@pytest.mark.parametrize("size", [SINGLE_COLUMN, DOUBLE_COLUMN])
def test_module_labels_do_not_overlap(size):
    _fig, ax = _draw_in(size)
    for side in _blocks(ax).values():
        side.sort()
        for (_, top), (bottom, _) in itertools.pairwise(side):
            assert top <= bottom + 0.5


def test_overlap_allowed_reproduces_web_app_rule():
    geom = _geom()
    ax = alluvial.draw(geom, avoid_label_overlap=False)
    fs = alluvial.get_artists(ax).module_labels[0].get_fontsize()
    (_, y0), (_, y1) = ax.transData.transform([(0, 0), (0, 1)])
    pt_per_px = (y1 - y0) * 72 / ax.figure.dpi  # module heights on the page, in points
    for n in geom.networks:
        for m in n.modules:
            if m.label is None:
                continue
            shown = [
                t
                for t in ax.texts
                if t.get_visible() and t.get_gid().startswith(f"module-label:{n.id}:{m.id}:")
            ]
            assert len(shown) == min(len(m.largest_leaf_names), amp._ts_max_lines(m.height * pt_per_px, fs))


def test_overlap_avoidance_hides_smaller_modules_first():
    _fig, ax = _draw_in(SINGLE_COLUMN, max_label_lines=1)
    geom = _geom()
    shown = {
        t.get_gid().rsplit(":", 1)[0] for t in _visible(ax.texts) if t.get_gid().startswith("module-label")
    }
    first = geom.networks[0]
    largest = max(first.modules, key=lambda m: m.flow)
    assert f"module-label:{first.id}:{largest.id}" in shown


def test_max_label_width_truncates_with_ellipsis():
    _fig, ax = _draw_in(DOUBLE_COLUMN, max_label_width=30)
    texts = _visible(alluvial.get_artists(ax).module_labels)
    assert any(t.get_text().endswith("…") for t in texts)
    for t in texts:
        assert t.get_window_extent().width * 72 / ax.figure.dpi <= 30 + 0.5
    full = {n for net in _geom().networks for m in net.modules for n in m.largest_leaf_names}
    for t in texts:
        assert t.get_text() in full or t.get_text()[:-1] in {n[: len(t.get_text()) - 1] for n in full}


def test_auto_label_width_caps_each_column_to_a_quarter():
    _fig, ax = _draw_in(SINGLE_COLUMN)
    w = ax.get_window_extent().width
    for t in _visible(alluvial.get_artists(ax).module_labels):
        assert t.get_window_extent().width <= 0.25 * w + 0.5


def test_no_truncation_on_own_figure_and_with_none():
    geom = _geom()
    full = {n for net in geom.networks for m in net.modules for n in m.largest_leaf_names}
    for ax in (alluvial.draw(geom), _draw_in(DOUBLE_COLUMN, geom, max_label_width=None)[1]):
        assert {t.get_text() for t in _visible(alluvial.get_artists(ax).module_labels)} <= full


def test_network_names_do_not_overlap():
    _fig, ax = _draw_in(SINGLE_COLUMN)  # long file names in a narrow axes
    boxes = sorted(
        (b.x0, b.x1) for b in (t.get_window_extent() for t in alluvial.get_artists(ax).network_labels)
    )
    assert len(boxes) == 4
    for (_, right), (left, _) in itertools.pairwise(boxes):
        assert right <= left
    assert all(t.get_text().endswith("…") for t in alluvial.get_artists(ax).network_labels)


def test_label_text_is_literal_not_mathtext():
    import dataclasses

    geom = _geom("planted-ftree__colored")
    nets = list(geom.networks)
    m0 = nets[0].modules[0]
    m0 = dataclasses.replace(m0, largest_leaf_names=("$5 price", "a_b$x$"))
    nets[0] = dataclasses.replace(nets[0], modules=(m0, *nets[0].modules[1:]))
    geom = dataclasses.replace(geom, networks=tuple(nets))
    ax = alluvial.draw(geom)
    ax.figure.canvas.draw()  # would raise on unbalanced "$" with mathtext
    assert "$5 price" in {t.get_text() for t in ax.texts}


def test_fontsize_in_points_and_relative():
    _fig, ax = _draw_in(SINGLE_COLUMN, fontsize=6.5, network_fontsize="large")
    art = alluvial.get_artists(ax)
    assert {t.get_fontsize() for t in art.module_labels} == {6.5}
    assert art.network_labels[0].get_fontsize() == pytest.approx(1.2 * plt.rcParams["font.size"])


# ------------------------------------------------------------------------------------------------- vector output


def _pdf_images(path):
    data = path.read_bytes()
    return [(int(w), int(h)) for w, h in re.findall(rb"/Height (\d+)[^>]*?/Width (\d+)", data)] or [
        (int(w), int(h)) for w, h in re.findall(rb"/Width (\d+)[^>]*?/Height (\d+)", data)
    ]


def test_gradients_embed_small_strips_in_pdf(tmp_path):
    geom = _geom()
    fig, ax = plt.subplots(figsize=DOUBLE_COLUMN)
    alluvial.draw(geom, ax)
    fig.savefig(tmp_path / "g.pdf")
    images = _pdf_images(tmp_path / "g.pdf")
    n_gradients = sum(isinstance(a, AxesImage) for a in alluvial.get_artists(ax).streamlines)
    assert n_gradients > 10
    assert len(images) >= n_gradients
    assert max(w * h for w, h in images) <= amp.GRADIENT_SAMPLES
    assert (tmp_path / "g.pdf").stat().st_size < 400_000


def test_rasterized_merges_shapes_keeps_text_vector(tmp_path):
    fig, ax = plt.subplots(figsize=DOUBLE_COLUMN)
    alluvial.draw(_geom(), ax, rasterized=True)
    art = alluvial.get_artists(ax)
    assert all(a.get_rasterized() for a in art.modules + art.streamlines)
    assert not any(t.get_rasterized() for t in ax.texts)
    fig.savefig(tmp_path / "r.pdf", dpi=150)
    assert len(re.findall(rb"/Subtype /Image", (tmp_path / "r.pdf").read_bytes())) <= 3


def test_svg_has_gids(tmp_path):
    fig, ax = plt.subplots(figsize=DOUBLE_COLUMN)
    alluvial.draw(_geom("planted-ftree__colored"), ax)
    fig.savefig(tmp_path / "d.svg")
    svg = (tmp_path / "d.svg").read_text()
    assert 'id="module:' in svg and 'id="streamline:' in svg and 'id="network-label:' in svg


# ------------------------------------------------------------------------------------------- seams and z-order


def test_module_hairline_hides_seams_by_default():
    ax = alluvial.draw(_geom("planted-ftree__colored"))
    for r in alluvial.get_artists(ax).modules:
        assert r.get_linewidth() == pytest.approx(0.3)
        assert r.get_edgecolor() == pytest.approx(r.get_facecolor())
    ax = alluvial.draw(_geom("planted-ftree__colored"), linewidth=0)
    assert all(r.get_linewidth() == 0 for r in alluvial.get_artists(ax).modules)
    ax = alluvial.draw(_geom("planted-ftree__colored"), edgecolor="k", linewidth=0.5)
    assert all(r.get_edgecolor() == to_rgba("k") for r in alluvial.get_artists(ax).modules)


def test_zorder_streamlines_under_modules_under_text():
    ax = alluvial.draw(_geom("planted-ftree__colored"))
    art = alluvial.get_artists(ax)
    zs = [a.get_zorder() for a in art.streamlines]
    assert zs == sorted(zs) and max(zs) < amp.Z_MODULE
    assert {r.get_zorder() for r in art.modules} == {amp.Z_MODULE}
    assert min(t.get_zorder() for t in ax.texts) > amp.Z_MODULE


# ---------------------------------------------------------------------------------------- styling passthrough


def test_style_dicts_pass_through():
    ax = alluvial.draw(
        _geom("planted-ftree__colored"),
        module_kw={"hatch": "//", "linewidth": 0.8},
        streamline_kw={"alpha": 0.4},
        text_kw={"family": "serif", "color": "0.2"},
        label_kw={"fontstyle": "italic"},
        network_label_kw={"fontweight": "bold", "color": "k"},
    )
    art = alluvial.get_artists(ax)
    assert all(r.get_hatch() == "//" and r.get_linewidth() == 0.8 for r in art.modules)
    assert all(a.get_alpha() == 0.4 for a in art.streamlines)
    assert all(t.get_fontstyle() == "italic" and t.get_color() == "0.2" for t in art.module_labels)
    assert all(t.get_fontweight() == "bold" and t.get_color() == "k" for t in art.network_labels)
    assert all("serif" in t.get_fontfamily() for t in ax.texts)


def test_palette_accepts_colormap_object():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom, palette=plt.get_cmap("tab10"), gradient=False)
    groups = [g for n in geom.networks for m in n.modules for g in m.groups]
    for g, r in zip(groups, alluvial.get_artists(ax).modules, strict=True):
        if g.highlight_index >= 0 and not g.insignificant:
            assert r.get_facecolor()[:3] == pytest.approx(to_rgb(plt.get_cmap("tab10")(g.highlight_index)))


def test_default_color_gray_and_insignificant_brighter():
    from alluvial._palette import brighter, to_rgb01

    geom = _geom("science-stree__default")
    ax = alluvial.draw(geom, default_color="0.6")
    groups = [g for n in geom.networks for m in n.modules for g in m.groups]
    gray = to_rgb01(brighter("#999999"))
    assert any(g.insignificant for g in groups)
    for g, r in zip(groups, alluvial.get_artists(ax).modules, strict=True):
        expected = gray if g.insignificant else to_rgb("0.6")
        assert r.get_facecolor()[:3] == pytest.approx(expected)


# ----------------------------------------------------------------------------------------------- artists, API


def test_get_artists():
    geom = _geom("planted-ftree__colored")
    ax = alluvial.draw(geom)
    art = alluvial.get_artists(ax)
    assert art.geometry is geom
    assert len(art.modules) == sum(len(m.groups) for n in geom.networks for m in n.modules)
    assert len(art.streamlines) == len(geom.streamlines)
    assert all(isinstance(a, (PathPatch, AxesImage)) for a in art.streamlines)
    assert all(isinstance(r, Rectangle) for r in art.modules)
    assert set(art.module_labels) | set(art.network_labels) == set(ax.texts)
    assert art.network_labels[0].get_gid() == f"network-label:{geom.networks[0].id}"
    _fig, other = plt.subplots()
    with pytest.raises(ValueError, match="no alluvial diagram"):
        alluvial.get_artists(other)


def test_plot_rejects_unknown_kwargs():
    with pytest.raises(TypeError, match="fontsiz"):
        alluvial.plot(["a.tree"], fontsiz=6)


def test_draw_does_not_show_or_touch_global_state(monkeypatch):
    monkeypatch.setattr(plt, "show", lambda *a, **k: pytest.fail("draw must not call plt.show"))
    rc = dict(plt.rcParams)
    _fig, ax = plt.subplots()
    alluvial.draw(_geom("planted-ftree__colored"), ax)
    assert plt.gca() is ax
    assert dict(plt.rcParams) == rc


def test_tall_axes_shows_more_names_than_the_layout_px_rule():
    """``name_candidates`` lets a tall axes / small font show more lines than the 600 px web view allows."""
    geom = alluvial.layout(
        [Path(__file__).parent / "data" / f"planted_t{i}.ftree" for i in range(2)], height=200
    )
    _fig, ax = _draw_in((4.0, 8.0), geom=geom, fontsize=5)
    extra = 0
    for n in geom.networks:
        for m in n.modules:
            if m.label is None:
                continue
            shown = [
                t.get_text()
                for t in _visible(ax.texts)
                if t.get_gid().startswith(f"module-label:{n.id}:{m.id}:")
            ]
            assert shown == list(m.name_candidates[: len(shown)])
            extra += max(0, len(shown) - len(m.largest_leaf_names))
    assert extra > 0
