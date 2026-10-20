"""Agg tests of the v2 renderer features: hierarchy shadows/outlines, the highlight legend, coloured label lines."""

from __future__ import annotations

import warnings

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest
from conftest import DATA_DIR
from matplotlib.colors import to_rgb
from matplotlib.patches import FancyBboxPatch, Rectangle

import alluvial
from alluvial import mpl as amp
from alluvial import palette

MULTILEVEL = [DATA_DIR / f"multilevel_t{i}.tree" for i in range(3)]
PLANTED = [DATA_DIR / f"planted_t{i}.ftree" for i in range(3)]
SIZES = [(3.4, 2.4), (7.0, 2.8)]
HIGHLIGHT = {"a": range(1, 21), "b": range(50, 71)}


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _draw_in(size, geom, **kw):
    fig, ax = plt.subplots(figsize=size, layout="constrained")
    alluvial.draw(geom, ax, **kw)
    fig.canvas.draw()
    return fig, ax


def _inside(inner, outer, tol=0.5):
    return (
        outer.x0 - tol <= inner.x0
        and inner.x1 <= outer.x1 + tol
        and outer.y0 - tol <= inner.y0
        and inner.y1 <= outer.y1 + tol
    )


# --------------------------------------------------------------------------------------------------- hierarchy


@pytest.mark.parametrize("mode", [True, "shadow", "outline"])
def test_hierarchy_draws_one_patch_per_outline(mode):
    geom = alluvial.layout(MULTILEVEL, module_level=3)
    _fig, ax = _draw_in(SIZES[0], geom, hierarchy=mode)
    art = alluvial.get_artists(ax)
    outlines = [(n.id, o) for n in geom.networks for o in sorted(n.outlines, key=lambda o: o.order)]
    assert len(art.outlines) == len(outlines) > 0
    assert [p.get_gid() for p in art.outlines] == [f"outline:{n}:{o.path}" for n, o in outlines]
    kind = FancyBboxPatch if mode == "outline" else Rectangle
    assert all(isinstance(p, kind) for p in art.outlines)
    if mode == "outline":
        # Round corners on screen whatever the data aspect.
        (x0, y0), (x1, y1) = ax.transData.transform([(0, 0), (1, 1)])
        assert art.outlines[0].get_mutation_aspect() == pytest.approx((x1 - x0) / (y1 - y0))
        assert min(p.get_zorder() for p in art.outlines) > max(s.get_zorder() for s in art.streamlines)
        assert max(p.get_zorder() for p in art.outlines) < amp.Z_MODULE
    else:
        assert {p.get_zorder() for p in art.outlines} == {amp.Z_SHADOW}
        assert to_rgb(art.outlines[0].get_facecolor()) == to_rgb(amp.SHADOW_COLOR)


def test_shadow_geometry_follows_the_web_app():
    geom = alluvial.layout(MULTILEVEL, module_level=3)
    ax = alluvial.draw(geom)
    art = alluvial.get_artists(ax)
    outline = sorted(geom.networks[1].outlines, key=lambda o: o.order)[0]
    patch = next(p for p in art.outlines if p.get_gid() == f"outline:{geom.networks[1].id}:{outline.path}")
    d = amp.SHADOW_OFFSET * (outline.max_level - outline.level)
    assert d > 0
    assert patch.get_xy() == pytest.approx((outline.x + d, geom.height - outline.y - outline.height - d))
    assert (patch.get_width(), patch.get_height()) == pytest.approx((outline.width, outline.height))


@pytest.mark.parametrize("mode", [False, None])
def test_hierarchy_off_and_flat_diagrams_draw_no_outlines(mode):
    ax = alluvial.draw(alluvial.layout(MULTILEVEL, module_level=2), hierarchy=mode)
    assert alluvial.get_artists(ax).outlines == []
    ax = alluvial.draw(alluvial.layout(MULTILEVEL))  # all top modules: nothing to draw
    assert alluvial.get_artists(ax).outlines == []


def test_hierarchy_rejects_unknown_modes():
    with pytest.raises(ValueError, match="hierarchy must be"):
        alluvial.draw(alluvial.layout(PLANTED), hierarchy="dots")


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("mode", ["shadow", "outline"])
def test_labels_and_names_clear_the_hierarchy_boxes(size, mode):
    geom = alluvial.layout(MULTILEVEL, module_level=2)
    _fig, ax = _draw_in(size, geom, hierarchy=mode)
    art = alluvial.get_artists(ax)
    boxes = [p.get_window_extent() for p in art.outlines]
    for t in art.module_labels + art.network_labels:
        if not t.get_visible() or not t.get_text():
            continue
        tb = t.get_window_extent()
        assert _inside(tb, ax.get_window_extent()), t.get_text()
        for b in boxes:
            overlap_x = min(tb.x1, b.x1) - max(tb.x0, b.x0)
            overlap_y = min(tb.y1, b.y1) - max(tb.y0, b.y0)
            assert overlap_x <= 0.5 or overlap_y <= 0.5, (t.get_text(), mode)
    for b in boxes:
        assert _inside(b, ax.get_window_extent(), tol=1.5)


def test_hierarchy_kw_styles_the_patches():
    geom = alluvial.layout(MULTILEVEL, module_level=2)
    ax = alluvial.draw(geom, hierarchy_kw={"facecolor": "red"})
    assert {to_rgb(p.get_facecolor()) for p in alluvial.get_artists(ax).outlines} == {(1.0, 0.0, 0.0)}


# ------------------------------------------------------------------------------------------------------ legend


@pytest.mark.parametrize("size", SIZES)
def test_legend_sits_above_the_diagram_inside_the_axes(size):
    geom = alluvial.layout(MULTILEVEL, highlight=HIGHLIGHT)
    _fig, ax = _draw_in(size, geom, legend=True)
    art = alluvial.get_artists(ax)
    leg = art.legend
    assert leg is not None and [t.get_text() for t in leg.get_texts()] == ["a", "b"]
    lb = leg.get_window_extent()
    assert _inside(lb, ax.get_window_extent())
    top_of_diagram = ax.transData.transform((0, geom.height))[1]
    assert lb.y0 >= top_of_diagram
    for t in art.module_labels:
        if t.get_visible():
            assert t.get_window_extent().y1 <= lb.y0 + 0.5, t.get_text()
    handles = leg.legend_handles if hasattr(leg, "legend_handles") else leg.legendHandles
    assert [to_rgb(h.get_facecolor()) for h in handles] == [
        palette.to_rgb01(h.color) for h in geom.highlight_labels
    ]


def test_legend_on_own_figure_fits():
    geom = alluvial.layout(MULTILEVEL, highlight=HIGHLIGHT)
    ax = alluvial.draw(geom, legend=True)
    ax.figure.canvas.draw()
    assert _inside(alluvial.get_artists(ax).legend.get_window_extent(), ax.figure.bbox)


def test_legend_function_replaces_and_accepts_matplotlib_placement():
    geom = alluvial.layout(MULTILEVEL, highlight=HIGHLIGHT)
    fig, ax = _draw_in(SIZES[0], geom)
    assert alluvial.get_artists(ax).legend is None
    leg = alluvial.legend(ax, other="other", title="groups")
    assert [t.get_text() for t in leg.get_texts()] == ["a", "b", "other"]
    assert ax.get_legend() is leg
    leg2 = alluvial.legend(ax, loc="upper left", bbox_to_anchor=(1, 1))
    assert ax.get_legend() is leg2 and alluvial.get_artists(ax).legend is leg2
    assert leg not in ax.get_children()
    fig.canvas.draw()
    # Placed by the caller: no room is reserved, so the diagram fills the axes again.
    assert ax.transData.transform((0, geom.height))[1] >= ax.get_window_extent().y1 - 30


def test_legend_palette_override_and_gray_labels():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        geom = alluvial.layout(MULTILEVEL, highlight=HIGHLIGHT, highlight_colors=["#b6b69f", "red"])
    ax = alluvial.draw(geom, legend=True, palette=["blue"])
    leg = alluvial.get_artists(ax).legend
    assert [t.get_text() for t in leg.get_texts()] == ["b"]  # "a" is drawn gray: no entry
    handles = leg.legend_handles if hasattr(leg, "legend_handles") else leg.legendHandles
    assert to_rgb(handles[0].get_facecolor()) == (0.0, 0.0, 1.0)


def test_legend_without_labels_warns():
    ax = alluvial.draw(alluvial.layout(PLANTED))
    with pytest.warns(UserWarning, match="no highlight labels.*use layout"):
        assert alluvial.legend(ax) is None


def test_legend_with_only_gray_labels_says_so():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        geom = alluvial.layout(MULTILEVEL, highlight={"a": HIGHLIGHT["a"]}, highlight_colors=["#b6b69f"])
    ax = alluvial.draw(geom)
    with pytest.warns(UserWarning, match="every label is drawn in the default"):
        assert alluvial.legend(ax) is None
    assert alluvial.legend(ax, other="other") is not None


# ----------------------------------------------------------------------------------------- label line colours


def _label_colors(ax):
    return {t.get_text(): to_rgb(t.get_color()) for t in alluvial.get_artists(ax).module_labels}


def test_label_lines_take_the_highlight_colour():
    geom = alluvial.layout(MULTILEVEL, highlight=HIGHLIGHT)
    colors = _label_colors(alluvial.draw(geom))
    by_label = {h.highlight_index: palette.to_rgb01(h.color) for h in geom.highlight_labels}
    seen = set()
    for n in geom.networks:
        for m in n.modules:
            if m.label is None:
                continue
            names = m.name_candidates or m.largest_leaf_names
            for name, hi in zip(names, m.name_highlight_indices):
                expected = by_label.get(hi, (0.0, 0.0, 0.0))
                assert colors[name] == expected, name
                seen.add(hi)
    assert seen >= {-1, 0, 1}


def test_label_colors_auto_is_black_without_highlight_and_can_be_forced():
    geom = alluvial.layout(PLANTED)  # similarity colours, no highlight labels
    assert set(_label_colors(alluvial.draw(geom)).values()) == {(0.0, 0.0, 0.0)}
    forced = set(_label_colors(alluvial.draw(geom, label_colors=True)).values())
    assert len(forced) > 1
    hl = alluvial.layout(PLANTED, highlight={"x": range(1, 30)})
    assert set(_label_colors(alluvial.draw(hl, label_colors=False)).values()) == {(0.0, 0.0, 0.0)}
    assert set(_label_colors(alluvial.draw(hl, label_kw={"color": "red"})).values()) == {(1.0, 0.0, 0.0)}
    with pytest.raises(ValueError, match="label_colors"):
        alluvial.draw(geom, label_colors="yes")


def test_plot_routes_v2_layout_and_draw_keywords():
    ax = alluvial.plot(MULTILEVEL, module_level=2, highlight=HIGHLIGHT, legend=True, hierarchy="outline")
    art = alluvial.get_artists(ax)
    assert art.outlines and art.legend is not None
    with pytest.raises(TypeError, match="unexpected keyword"):
        alluvial.plot(MULTILEVEL, levels=2)
