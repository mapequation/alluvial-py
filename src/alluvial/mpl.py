"""Thin matplotlib renderer for ``AlluvialGeometry``.

``draw`` maps the layout's y-down coordinates with ``y -> height - y`` so the largest module is at the bottom.

Shapes live in data coordinates (layout px). Every text size, gap and margin is in points, so the figure reads the
same at any axes size. The labels and axes limits are fitted again at every draw by an invisible ``_Fitter``
artist, so the diagram adapts to layout engines (``layout="constrained"``), ``fig.set_size_inches`` and savefig.
"""

# Spec: docs/dev/design.md (Coordinates, Public API, Changes after review) and port-notes/colors-render.md §7,
# streamlines.md §8.

from __future__ import annotations

import inspect
import itertools
import math
import numbers
import warnings
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colormaps
from matplotlib import colors as mcolors
from matplotlib import transforms as mtransforms
from matplotlib.artist import Artist
from matplotlib.font_manager import FontProperties
from matplotlib.legend import Legend
from matplotlib.patches import FancyBboxPatch, Patch, PathPatch, Rectangle
from matplotlib.path import Path
from matplotlib.text import Text
from matplotlib.textpath import text_to_path

from . import _palette
from ._warnings import user_stacklevel

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.backend_bases import RendererBase

    from .geometry import AlluvialGeometry, ModuleGeometry

__all__ = ["AlluvialArtists", "draw", "get_artists", "legend", "plot"]

# colors-render.md §7.4-7.5
GRADIENT_STOPS = (0.15, 0.85)
GRADIENT_SAMPLES = 256
LINE_HEIGHT_EM = 1.2
FIT_LINE_HEIGHT_EM = 1.8
ELLIPSIS = "…"

# Margins, in points.
PAD_PT = 2.0
NAME_GAP_EM = 0.4  # gap between the diagram (or the lowest label) and the network names, in network-font em
AUTO_LABEL_WIDTH_FRACTION = (
    0.25  # "auto" max_label_width: each label column takes at most this share of the axes
)
MIN_DIAGRAM_FRACTION = 0.05

Z_SHADOW = 0.5
Z_STREAMLINE = 1.0
Z_MODULE = 2.0
Z_TEXT = 3.0

# The web app's hierarchy rendering (v2-hierarchy.md §9): ShadowModule / OutlineModule.
SHADOW_OFFSET = 5.0  # hierarchicalModuleOffset, layout px per level below the deepest
SHADOW_COLOR = "#a4a4b0"  # #b6b69f at opacity 0.5 with mix-blend-mode difference, over white
# A solid thin dark gray line instead of the web app's dotted (strokeDasharray 1,4) light outline.
OUTLINE_COLOR = "0.3"
OUTLINE_LINEWIDTH = 0.8  # points
# Size of a figure draw() makes itself, in inches (see _figure_size).
FIG_HEIGHT_BASE = 1.0
FIG_HEIGHT_PER_MODULE = 0.28
FIG_HEIGHT_RANGE = (2.0, 6.0)
FIG_WIDTH_BASE = 0.4  # the first network
FIG_WIDTH_PER_NETWORK = 1.1  # each further network with its streamlines
FIG_DIAGRAM_MAX_WIDTH = 12.0
LEGEND_GAP_EM = 0.6  # gap between the legend and the top of the diagram (or its labels), in label-font em
HIERARCHY_MODES = ("shadow", "outline")

RGB = tuple[float, float, float]


# --------------------------------------------------------------------------------------------------------- colors


class _Colors:
    """``make_fill`` with matplotlib color specs: palette cycling, insignificant groups brighter."""

    def __init__(self, palette: Sequence[Any], default_color: Any) -> None:
        # A None entry is a JS ``undefined`` in the store's highlightColors, which the browser fills black.
        self._palette = ["#000000" if c is None else _css(c) for c in palette]
        self._default = _css(default_color)
        self._cache: dict[tuple[int, bool], RGB] = {}
        self.cycled: set[int] = set()
        self.invalid: set[int] = set()

    def __call__(self, highlight_index: int, insignificant: bool = False) -> RGB:
        key = (highlight_index, insignificant)
        if key not in self._cache:
            self._cache[key] = self._resolve(highlight_index, insignificant)
        return self._cache[key]

    def _resolve(self, highlight_index: int, insignificant: bool) -> RGB:
        if highlight_index == _palette.NOT_HIGHLIGHTED:
            color = self._default
        elif highlight_index >= 0 and self._palette:
            if highlight_index >= len(self._palette):
                self.cycled.add(highlight_index)
            color = self._palette[highlight_index % len(self._palette)]
        else:
            self.invalid.add(highlight_index)
            color = self._default
        if insignificant:
            color = _palette.brighter(color, _palette.INSIGNIFICANT_BRIGHTER_K)
        return _palette.to_rgb01(color)

    def text(self, highlight_index: int, insignificant: bool = False) -> RGB:
        """Label-line color (web ``highlightColor("#000", highlightColors)``): black when not highlighted or out of
        the palette, brighter for insignificant names."""
        if 0 <= highlight_index < len(self._palette):
            color = self._palette[highlight_index]
            if insignificant:
                color = _palette.brighter(color, _palette.INSIGNIFICANT_BRIGHTER_K)
            return _palette.to_rgb01(color)
        return (0.0, 0.0, 0.0)

    def warn(self) -> None:
        n = len(self._palette)
        if self.cycled:
            warnings.warn(
                f"highlight indices up to {max(self.cycled)} exceed the palette of {n} colors; cycling the palette",
                UserWarning,
                stacklevel=user_stacklevel(),
            )
        if self.invalid:
            warnings.warn(
                f"highlight indices {sorted(self.invalid)} have no palette color; using the default color",
                UserWarning,
                stacklevel=user_stacklevel(),
            )


def _css(color: Any) -> str:
    if isinstance(color, str) and color.lstrip().startswith("rgb("):
        return color
    return mcolors.to_hex(color, keep_alpha=False)


def _max_highlight_index(geometry: AlluvialGeometry) -> int:
    best = -1
    for network in geometry.networks:
        for module in network.modules:
            for group in module.groups:
                best = max(best, group.highlight_index)
    for s in geometry.streamlines:
        best = max(best, s.left_highlight_index, s.right_highlight_index)
    return best


def _resolve_palette(
    palette: Sequence[Any] | str | mcolors.Colormap | None, geometry: AlluvialGeometry
) -> list[Any]:
    if palette is None:
        return list(geometry.palette)
    if isinstance(palette, str):
        try:
            palette = colormaps[palette]
        except KeyError:
            raise ValueError(f"palette {palette!r} is not a matplotlib colormap name") from None
    if isinstance(palette, mcolors.Colormap):
        if isinstance(palette, mcolors.ListedColormap) and palette.N < 256:
            return [palette(i) for i in range(palette.N)]
        n = max(_max_highlight_index(geometry) + 1, 1)
        return [palette(v) for v in (np.linspace(0, 1, n) if n > 1 else [0.0])]
    return list(palette)


# ------------------------------------------------------------------------------------------------------- artists


@dataclass
class AlluvialArtists:
    """The artists ``draw`` added to an axes, for restyling after the fact. Get it with ``get_artists(ax)``.

    Every artist also carries a ``gid`` (kept as the element id in SVG output): ``module:<network id>:<module id>:<group>``,
    ``streamline:<streamline id>``, ``module-label:<network id>:<module id>:<line>``, ``network-label:<network id>`` and
    ``outline:<network id>:<module path>``.

    Attributes
    ----------
    geometry : AlluvialGeometry
        The geometry that was drawn.
    modules : list of matplotlib.patches.Rectangle
        One rectangle per module group, in geometry order.
    streamlines : list of matplotlib.artist.Artist
        One per streamline in geometry (draw) order: a ``PathPatch``, or a clipped ``AxesImage`` for gradients.
    module_labels : list of matplotlib.text.Text
        One text per label line. Lines that do not fit are invisible; the fitter decides at every draw.
    network_labels : list of matplotlib.text.Text
        One per network with a name.
    outlines : list of matplotlib.patches.Patch
        One per super-module box (``NetworkGeometry.outlines``) when drawn with ``hierarchy``: a shadow
        ``Rectangle`` or a dotted ``FancyBboxPatch``.
    legend : matplotlib.legend.Legend or None
        The highlight legend, from ``draw(..., legend=True)`` or ``alluvial.legend(ax)``.

    Examples
    --------
    >>> import alluvial
    >>> ax = alluvial.plot([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], names=["2020", "2021"])
    >>> artists = alluvial.get_artists(ax)
    >>> len(artists.modules), len(artists.streamlines), [text.get_text() for text in artists.network_labels]
    (4, 3, ['2020', '2021'])
    >>> artists.network_labels[0].get_gid()
    'network-label:net0'
    """

    geometry: AlluvialGeometry
    modules: list[Rectangle] = field(default_factory=list)
    streamlines: list[Artist] = field(default_factory=list)
    module_labels: list[Text] = field(default_factory=list)
    network_labels: list[Text] = field(default_factory=list)
    outlines: list[Patch] = field(default_factory=list)
    legend: Legend | None = None
    _colors: Any = field(default=None, repr=False, compare=False)


def get_artists(ax: Axes) -> AlluvialArtists:
    """The ``AlluvialArtists`` of the last diagram drawn on ``ax``.

    Examples
    --------
    >>> import alluvial
    >>> ax = alluvial.plot([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], names=["2020", "2021"])
    >>> artists = alluvial.get_artists(ax)
    >>> for text in artists.network_labels:
    ...     text.set_fontweight("bold")
    >>> for patch in artists.streamlines:
    ...     patch.set_alpha(0.5)
    """
    return _fitter(ax).artists


def _fitter(ax: Axes) -> _Fitter:
    fitters = [a for a in ax.get_children() if isinstance(a, _Fitter)]
    if not fitters:
        raise ValueError("no alluvial diagram has been drawn on this axes")
    return fitters[-1]


def _streamline_patch(points: list[tuple[int, tuple[float, float]]], height: float, **kw: Any) -> PathPatch:
    codes = [code for code, _ in points]
    verts = [(x, height - y) for _, (x, y) in points]
    return PathPatch(Path(verts, codes), **kw)


def _gradient(left: RGB, right: RGB) -> np.ndarray:
    t = np.linspace(0.0, 1.0, GRADIENT_SAMPLES)
    lo, hi = GRADIENT_STOPS
    u = np.clip((t - lo) / (hi - lo), 0.0, 1.0)[:, None]
    return ((1 - u) * np.asarray(left) + u * np.asarray(right))[None, :, :]


# ---------------------------------------------------------------------------------------------------- text fitting


def _ts_max_lines(module_height_pt: float, fontsize: float) -> int:
    """The web app's multi-line fit rule (colors-render.md §7.5), with the module height in points."""
    max_lines = math.ceil(module_height_pt / (fontsize * FIT_LINE_HEIGHT_EM))
    if max_lines % 2 == 0:
        max_lines -= 1
    return max(max_lines, 0)


def _measure(text: Text, s: str, renderer: RendererBase | None = None) -> tuple[float, float, float]:
    """Width, height and descent of ``s`` in points with ``text``'s font.

    With a renderer, its own metrics (Agg hints glyphs at the output dpi, so text is up to ~7% wider than the
    outline metrics); without one, the font outline metrics.
    """
    if not s:
        return 0.0, 0.0, 0.0
    if text.get_usetex():
        ismath: Any = "TeX"
    else:
        try:
            s, ismath = text._preprocess_math(s)
        except AttributeError:  # pragma: no cover - private API changed
            ismath = False
    prop = text.get_fontproperties()
    key = None
    if ismath != "TeX":  # TeX metrics depend on the preamble; not cached
        key = (
            s,
            ismath,
            _font_key(prop),
            None
            if renderer is None  # MixedModeRenderer (PDF, SVG, PS) wraps the backend's renderer
            else (type(renderer), type(getattr(renderer, "_renderer", None)), renderer.points_to_pixels(1.0)),
            tuple(mpl.rcParams[k] for k in _MEASURE_RCPARAMS),
        )
        cached = _MEASURE_CACHE.get(key)
        if cached is not None:
            return cached
    if renderer is None:
        out = tuple(text_to_path.get_text_width_height_descent(s, prop, ismath=ismath))
    else:
        w, h, d = renderer.get_text_width_height_descent(s, prop, ismath=ismath)
        px_per_pt = renderer.points_to_pixels(1.0)
        out = (w / px_per_pt, h / px_per_pt, d / px_per_pt)
    if key is not None:
        if len(_MEASURE_CACHE) >= _MEASURE_CACHE_SIZE:
            _MEASURE_CACHE.clear()
        _MEASURE_CACHE[key] = out
    return out


# Text metrics by (string, math mode, font, renderer type and scale, rcParams): every fit truncates and measures
# every candidate label line, and a draw plus a savefig fit twice (thousands of labels for a sub-module diagram).
_MEASURE_CACHE: dict[tuple[Any, ...], tuple[float, float, float]] = {}
_MEASURE_CACHE_SIZE = 200_000
_MEASURE_RCPARAMS = ("text.hinting", "text.hinting_factor", "text.kerning_factor", "mathtext.fontset")


def _font_key(prop: Any) -> tuple[Any, ...]:
    """The fields of ``FontProperties.__hash__``, as a tuple (FontProperties is mutable)."""
    return (
        tuple(prop.get_family()),
        prop.get_slant(),
        prop.get_variant(),
        prop.get_weight(),
        prop.get_stretch(),
        prop.get_size(),
        prop.get_file(),
        prop.get_math_fontfamily(),
    )


def _truncate(text: Text, s: str, max_width: float | None, renderer: RendererBase | None = None) -> str:
    """``s``, or its longest prefix plus an ellipsis whose width is ``<= max_width`` points (``""`` if none fits)."""
    if max_width is None or _measure(text, s, renderer)[0] <= max_width:
        return s
    lo, hi = 0, len(s)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _measure(text, s[:mid].rstrip() + ELLIPSIS, renderer)[0] <= max_width:
            lo = mid
        else:
            hi = mid - 1
    if lo == 0:
        return ELLIPSIS if _measure(text, ELLIPSIS, renderer)[0] <= max_width else ""
    return s[:lo].rstrip() + ELLIPSIS


@dataclass
class _Block:
    """The label of one module: up to ``len(texts)`` lines, largest name first."""

    module: ModuleGeometry
    side: int  # -1 left of the first network, +1 right of the last
    names: list[str]
    texts: list[Text]
    x: float  # data x of the module edge the label hangs off
    y: float  # data y of the module center
    fontsize: float
    half_x: float  # half the x-height, points
    shown: list[str] = field(default_factory=list)
    widths: list[float] = field(default_factory=list)
    avail: int = 0
    n: int = 0

    def extent(self, n: int, sy: float) -> tuple[float, float]:
        """Bottom and top of an ``n``-line block in points above the diagram bottom."""
        line_h = LINE_HEIGHT_EM * self.fontsize
        center = math.ceil(n / 2) - 1
        yc = self.y * sy
        return yc - (n - 1 - center) * line_h - 0.5 * line_h, yc + center * line_h + 0.5 * line_h


@dataclass
class _Solution:
    limits: tuple[float, float, float, float]
    bottom: float  # label overflow below the diagram, points
    names: list[str]
    overflow: bool  # the labels squeeze the diagram below MIN_DIAGRAM_FRACTION of the axes
    top: float = 0.0  # label overflow above the diagram, points
    sx: float = 1.0  # points per px
    sy: float = 1.0


class _Fitter(Artist):
    """Invisible artist that fits the labels and the axes limits to the axes size before anything else is drawn.

    Shapes are in data units (layout px); texts, gaps and margins in points. Given the axes size in points it picks the
    label lines (the web app's fit rule, then ``avoid_label_overlap``), truncates labels and network names, and sets
    limits so the diagram fills the axes and every text stays inside it.
    """

    def __init__(
        self,
        ax: Axes,
        geometry: AlluvialGeometry,
        artists: AlluvialArtists,
        blocks: list[_Block],
        names: list[tuple[Text, float, str]],
        *,
        label_pad: float,
        max_label_width: float | str | None,
        avoid_label_overlap: bool,
    ) -> None:
        super().__init__()
        self.set_in_layout(False)
        self.set_zorder(-math.inf)
        self._ax = ax
        self._W = float(geometry.width)
        self._H = float(geometry.height)
        self.artists = artists
        self._blocks = blocks
        self._names = names
        self._label_pad = label_pad
        self._max_label_width = max_label_width
        self._avoid = avoid_label_overlap
        self.overflow = False
        self.legend: Legend | None = None  # placed above the diagram; the fit reserves its height
        self._legend_gap = 0.0
        # Data px the hierarchy boxes stick out of the diagram rect: left, right, bottom, top.
        self.extents = (0.0, 0.0, 0.0, 0.0)

    def set_legend(self, legend: Legend | None, gap: float = 0.0) -> None:
        self.legend = legend
        self._legend_gap = gap
        self.stale = True

    def _legend_size(self, renderer: RendererBase | None) -> tuple[float, float]:
        """Width and height of the managed legend (plus its gap) in points, ``(0, 0)`` without one."""
        if self.legend is None or not self.legend.get_visible():
            return 0.0, 0.0
        if renderer is None:
            renderer = self._ax.figure._get_renderer()
        bbox = self.legend.get_window_extent(renderer)
        to_pt = 72.0 / self._ax.figure.dpi
        return bbox.width * to_pt, bbox.height * to_pt + self._legend_gap

    def get_window_extent(self, renderer: RendererBase | None = None) -> mtransforms.Bbox:
        return mtransforms.Bbox.null()  # nothing visible of its own

    def draw(self, renderer: RendererBase) -> None:
        if self.get_visible():
            self.fit(renderer)
        self.stale = False

    def axes_size_pt(self, renderer: RendererBase | None = None) -> tuple[float, float]:
        bbox = self._ax.get_window_extent(renderer)
        to_pt = 72.0 / self._ax.figure.dpi
        return bbox.width * to_pt, bbox.height * to_pt

    # ------------------------------------------------------------------------------------------------ fitting

    def fit(self, renderer: RendererBase | None, native: bool = False) -> tuple[float, float, float, float]:
        """Fit labels and limits to the axes and apply them; return the limits.

        With ``native``, solve at one point per px instead, with untruncated labels (``draw`` measures the label space
        of its own figure so).
        """
        sol = (
            self._solve(None, None, renderer)
            if native
            else self._solve(*self.axes_size_pt(renderer), renderer)
        )
        self.overflow = sol.overflow
        self._apply(sol)
        return sol.limits

    def _solve(self, w_pt: float | None, h_pt: float | None, renderer: RendererBase | None) -> _Solution:
        W, H = max(self._W, 1e-9), max(self._H, 1e-9)
        fixed = w_pt is None or h_pt is None
        cap = self._max_label_width
        if cap == "auto":
            cap = None if fixed else max(AUTO_LABEL_WIDTH_FRACTION * w_pt - self._label_pad - PAD_PT, 0.0)

        # Truncated label lines and their widths do not depend on the scale. A line that cannot show even an
        # ellipsis ends the block.
        for b in self._blocks:
            b.shown = [_truncate(t, s, cap, renderer) for t, s in zip(b.texts, b.names, strict=True)]
            b.widths = [_measure(t, s, renderer)[0] for t, s in zip(b.texts, b.shown, strict=True)]
            b.avail = b.shown.index("") if "" in b.shown else len(b.shown)

        # Vertical: points per px, shrinking until the label overflow and the network names fit.
        name_space = max(
            ((NAME_GAP_EM + LINE_HEIGHT_EM) * t.get_fontsize() for t, _, _ in self._names), default=0.0
        )
        if fixed:
            sy = 1.0
        else:
            sy = max((h_pt - name_space - 2 * PAD_PT) / H, MIN_DIAGRAM_FRACTION * h_pt / H)
            for _ in range(20):
                self._place(sy)
                top, bottom = self._vertical(sy)
                new = max(
                    (h_pt - top - bottom - name_space - 2 * PAD_PT) / H, MIN_DIAGRAM_FRACTION * h_pt / H
                )
                if new >= sy - 1e-9:
                    break
                sy = new
        legend_w, legend_h = self._legend_size(renderer)
        if fixed:
            sy = 1.0
        elif legend_h:
            # Shrink the vertical scale until the legend fits above the labels.
            for _ in range(20):
                self._place(sy)
                top, bottom = self._vertical(sy)
                new = max(
                    (h_pt - top - bottom - name_space - legend_h - 2 * PAD_PT) / H,
                    MIN_DIAGRAM_FRACTION * h_pt / H,
                )
                if new >= sy - 1e-9:
                    break
                sy = new
        self._place(sy)
        top, bottom = self._vertical(sy)
        T = top + legend_h + PAD_PT
        B = bottom + name_space + PAD_PT

        # Horizontal: label columns, then network names truncated to the space between network centers.
        left = max((w for b in self._blocks if b.side < 0 for w in b.widths[: b.n]), default=None)
        right = max((w for b in self._blocks if b.side > 0 for w in b.widths[: b.n]), default=None)
        L0 = PAD_PT + (0.0 if left is None else left + self._label_pad)
        R0 = PAD_PT + (0.0 if right is None else right + self._label_pad)
        L, R = L0, R0
        sx = 1.0
        eL, eR = self.extents[:2]
        WE = W + eL + eR
        min_sx = 0.0 if fixed else MIN_DIAGRAM_FRACTION * w_pt / WE
        shown = [s for _, _, s in self._names]
        centers = [x for _, x, _ in self._names]
        for _ in range(5):
            sx = 1.0 if fixed else max((w_pt - L - R) / WE, min_sx)
            L, R = L0, R0
            for i, (t, x, s) in enumerate(self._names):
                gaps = [abs(centers[j] - x) * sx for j in (i - 1, i + 1) if 0 <= j < len(centers)]
                avail = min(gaps) - 0.5 * t.get_fontsize() if gaps else None
                shown[i] = _truncate(t, s, avail, renderer)
                half = 0.5 * _measure(t, shown[i], renderer)[0]
                L = max(L, half - (x + eL) * sx + PAD_PT)
                R = max(R, half - (self._W + eR - x) * sx + PAD_PT)
            if fixed or (abs(L - L0) < 1e-6 and abs(R - R0) < 1e-6):
                break
            L0, R0 = L, R

        if fixed:
            extra = max(legend_w + 2 * PAD_PT - (WE + L + R), 0.0) / 2
            limits = (-eL - L - extra, self._W + eR + R + extra, -B, self._H + T)
            return _Solution(limits, bottom, shown, False, top)
        x0, y0 = -eL - L / sx, -B / sy
        overflow = (w_pt - L - R) / WE < min_sx - 1e-9 or (
            h_pt - T - B
        ) / H < MIN_DIAGRAM_FRACTION * h_pt / H - 1e-9
        return _Solution((x0, x0 + w_pt / sx, y0, y0 + h_pt / sy), bottom, shown, overflow, top, sx, sy)

    def _place(self, sy: float) -> None:
        """Choose the number of lines of every block at ``sy`` points per px."""
        for side in (-1, 1):
            blocks = [b for b in self._blocks if b.side == side]
            # Larger modules claim space first; ties keep layout order.
            order = sorted(range(len(blocks)), key=lambda i: -blocks[i].module.flow)
            placed: list[tuple[float, float]] = []
            for i in order:
                b = blocks[i]
                n_max = min(b.avail, _ts_max_lines(b.module.height * sy, b.fontsize))
                b.n = 0
                for n in range(n_max, 0, -1) if self._avoid else ([n_max] if n_max else []):
                    lo, hi = b.extent(n, sy)
                    if not self._avoid or all(
                        hi <= p_lo + 1e-6 or lo >= p_hi - 1e-6 for p_lo, p_hi in placed
                    ):
                        b.n = n
                        placed.append((lo, hi))
                        break

    def _vertical(self, sy: float) -> tuple[float, float]:
        """Label (or hierarchy box) overflow above the diagram top and below its bottom, in points, for the current
        placement."""
        top, bottom = self.extents[3] * sy, self.extents[2] * sy
        for b in self._blocks:
            if b.n:
                lo, hi = b.extent(b.n, sy)
                top = max(top, hi - self._H * sy)
                bottom = max(bottom, -lo)
        return top, bottom

    def _apply(self, sol: _Solution) -> None:
        ax = self._ax
        fig, data = ax.figure, ax.transData
        for b in self._blocks:
            center = math.ceil(b.n / 2) - 1
            for k, t in enumerate(b.texts):
                t.set_visible(k < b.n)
                if k < b.n:
                    dy = -(k - center) * LINE_HEIGHT_EM * b.fontsize - b.half_x
                    t.set_text(b.shown[k])
                    t.set_transform(
                        mtransforms.offset_copy(
                            data, fig=fig, x=b.side * self._label_pad, y=dy, units="points"
                        )
                    )
        for (t, _, _), s in zip(self._names, sol.names, strict=True):
            dy = -(sol.bottom + NAME_GAP_EM * t.get_fontsize())
            t.set_text(s)
            t.set_transform(mtransforms.offset_copy(data, fig=fig, x=0.0, y=dy, units="points"))
        for patch in self.artists.outlines:
            if isinstance(patch, FancyBboxPatch):
                # Round corners on screen: the rounding size is in x data units.
                patch.set_mutation_aspect(sol.sx / sol.sy)
        if self.legend is not None:
            anchor = mtransforms.blended_transform_factory(
                ax.transAxes,
                mtransforms.offset_copy(data, fig=fig, x=0.0, y=sol.top + self._legend_gap, units="points"),
            )
            self.legend.set_bbox_to_anchor((0.5, self._H), transform=anchor)
        if not np.allclose(sol.limits, (*ax.get_xlim(), *ax.get_ylim()), rtol=1e-9, atol=1e-9):
            ax.set_xlim(*sol.limits[:2])
            ax.set_ylim(*sol.limits[2:])


def _figure_height(geometry: AlluvialGeometry) -> float:
    """Height in inches of a figure ``draw`` makes itself: grows with the modules of the fullest network."""
    n = max((len(network.modules) for network in geometry.networks), default=0)
    lo, hi = FIG_HEIGHT_RANGE
    return min(max(FIG_HEIGHT_BASE + FIG_HEIGHT_PER_MODULE * n, lo), hi)


def _figure_width(geometry: AlluvialGeometry, label_pt: float, name_pt: float = 0.0) -> float:
    """Width in inches of a figure ``draw`` makes itself: per network, plus the labels (at most as wide again).

    ``name_pt`` is the space a network name needs between network centers; the diagram widens to give it, and the
    margins hold half a name on each side.
    """
    n = max(len(geometry.networks), 1)
    diagram = FIG_WIDTH_BASE + FIG_WIDTH_PER_NETWORK * (n - 1)
    xs = [network.x + 0.5 * network.width for network in geometry.networks]
    min_dx = min((b - a for a, b in itertools.pairwise(xs)), default=0.0)
    if name_pt > 0 and min_dx > 0:
        diagram = max(diagram, name_pt / min_dx * float(geometry.width) / 72)
    diagram = min(diagram, FIG_DIAGRAM_MAX_WIDTH)
    return diagram + min(max(label_pt, name_pt, 0.0) / 72, diagram)


def _check_draw_args(geometry: Any, ax: Any) -> None:
    from matplotlib.axes import Axes

    from .geometry import AlluvialGeometry

    if not isinstance(geometry, AlluvialGeometry):
        raise TypeError(
            f"draw() takes the AlluvialGeometry returned by alluvial.layout, got {type(geometry).__name__}; to lay "
            "out and draw networks in one call, use alluvial.plot(networks, ax=ax)"
        )
    if ax is not None and not isinstance(ax, Axes):
        hint = (
            "pass one of them, e.g. axs[0]" if isinstance(ax, np.ndarray) else "e.g. fig, ax = plt.subplots()"
        )
        raise TypeError(f"ax must be a matplotlib Axes, got {type(ax).__name__}; {hint}")


def _x_height(text: Text) -> float:
    _, h, d = text_to_path.get_text_width_height_descent("x", text.get_fontproperties(), ismath=False)
    return h - d


def _fontsize_pt(size: float | str | None, default: str) -> float:
    return FontProperties(size=default if size is None else size).get_size_in_points()


# ------------------------------------------------------------------------------------------------------------ draw


def draw(
    geometry: AlluvialGeometry,
    ax: Axes | None = None,
    *,
    palette: Sequence[Any] | str | mcolors.Colormap | None = None,
    default_color: Any = None,
    module_labels: bool = True,
    network_labels: bool = True,
    fontsize: float | str | None = None,
    network_fontsize: float | str | None = None,
    max_label_lines: int | None = None,
    max_label_width: float | str | None = "auto",
    avoid_label_overlap: bool = True,
    label_pad: float = 3.0,
    streamline_alpha: float = 0.8,
    gradient: bool = True,
    edgecolor: Any = "face",
    linewidth: float = 0.3,
    rasterized: bool = False,
    hierarchy: bool | str | None = True,
    legend: bool = False,
    label_colors: bool | str = "auto",
    module_kw: dict[str, Any] | None = None,
    streamline_kw: dict[str, Any] | None = None,
    hierarchy_kw: dict[str, Any] | None = None,
    text_kw: dict[str, Any] | None = None,
    label_kw: dict[str, Any] | None = None,
    network_label_kw: dict[str, Any] | None = None,
) -> Axes:
    """Draw a laid-out alluvial diagram on a matplotlib Axes.

    The shapes are in layout px (data coordinates, y up); every text size, gap and margin is in points. At each draw
    the labels and the axes limits are fitted to the axes size, so the diagram fills the axes, every text stays inside
    it and font sizes are exact at any figure size (also under ``layout="constrained"`` and after resizing).

    Parameters
    ----------
    geometry : AlluvialGeometry
        Result of ``alluvial.layout``.
    ax : matplotlib.axes.Axes, optional
        Target axes, drawn on at its size. By default a new figure is created, sized by content: 1.0 + 0.28 in per
        module of the network with the most modules (between 2 and 6 in) tall, and 0.4 + 1.1 in per further network
        wide, plus the width of the labels (at most as much again).
    palette : sequence of colors, str or Colormap, optional
        Highlight colors, or a matplotlib colormap (name). Qualitative maps are used as is, continuous maps are
        sampled to the needed number of colors. Defaults to ``geometry.palette``. Indices beyond the palette cycle
        it, with a warning.
    default_color : color, optional
        Color of unhighlighted modules; defaults to the web app's gray.
    module_labels, network_labels : bool, default True
        Draw module name labels (first and last network) and network names (below each network).
    fontsize : float or str, optional
        Module label size in points or a relative size; defaults to ``"small"`` (``rcParams["font.size"]`` / 1.2).
    network_fontsize : float or str, optional
        Network name size; defaults to ``"medium"`` (``rcParams["font.size"]``).
    max_label_lines : int, optional
        Cap on the names (lines) per module label. By default as many as fit (the web app rule: one line per
        1.8 em of module height, an odd number).
    max_label_width : float, "auto" or None, default "auto"
        Longer label lines are truncated with an ellipsis to this width in points. ``"auto"`` keeps each label
        column within a quarter of the axes width; None never truncates.
    avoid_label_overlap : bool, default True
        Where labels of neighboring modules would overlap, drop lines of the smaller module, then its whole label.
        False reproduces the web app, which lets them overlap.
    label_pad : float, default 3
        Gap between a module and its label, in points.
    streamline_alpha : float, default 0.8
        Streamline opacity.
    gradient : bool, default True
        Fill streamlines whose ends differ in color with a horizontal gradient (as the web app does; a small
        embedded image, clipped to the streamline). If False they use the color of their left end, all vector.
    edgecolor, linewidth : default "face", 0.3
        Module edge style. The default hairline in the face color hides the antialiasing seams between stacked
        groups and at streamline ends; use ``linewidth=0`` for exact web app rectangles.
    rasterized : bool, default False
        Rasterize modules and streamlines (texts stay vector) in PDF/SVG output, for very large diagrams.
    hierarchy : bool or {"shadow", "outline"}, default True
        How to show the parent modules of expanded sub-modules (``NetworkGeometry.outlines``, from
        ``layout(module_level=...)`` or ``expand=``), as the web app does: ``"shadow"`` (or True) draws a gray box
        behind each parent, offset right and down by 5 px per level; ``"outline"`` a thin solid dark gray rounded
        box around it (the web app's is dotted).
        False or None draws nothing. A diagram of top modules has no outlines either way.
    legend : bool, default False
        Add a legend of the highlight labels (``layout(highlight=...)``) above the diagram; see ``alluvial.legend``.
    label_colors : bool or "auto", default "auto"
        Color each module label line by its node's highlight color, as the web app does (black when gray).
        ``"auto"`` does so only for a diagram with highlight labels (``layout(highlight=...)``), where the color
        tells which names belong to a group.
    module_kw, streamline_kw : dict, optional
        Extra ``Rectangle`` / streamline properties (e.g. ``{"hatch": "//", "edgecolor": "white"}``,
        ``{"alpha": 0.6}``). A hatch is drawn in the edge color, which is the face color by default.
    hierarchy_kw : dict, optional
        Extra properties of the hierarchy shadows or outlines (e.g. ``{"facecolor": "0.85"}``,
        ``{"edgecolor": "k", "linewidth": 1.5}``, ``{"linestyle": "--"}``).
    text_kw : dict, optional
        Extra ``Text`` properties for all labels (e.g. ``{"family": "serif"}``).
    label_kw, network_label_kw : dict, optional
        Extra ``Text`` properties for module labels or network names only (override ``text_kw``).

    Returns
    -------
    matplotlib.axes.Axes
        The axes drawn on, with the axis turned off. ``get_artists(ax)`` returns the created artists.

    Examples
    --------
    >>> import alluvial
    >>> import matplotlib.pyplot as plt
    >>> geometry = alluvial.layout([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], names=["2020", "2021"])
    >>> fig, ax = plt.subplots(figsize=(3.4, 2.4), layout="constrained")
    >>> ax = alluvial.draw(geometry, ax, fontsize=6, max_label_lines=3)
    >>> fig.savefig("alluvial.pdf")
    """
    _check_draw_args(geometry, ax)
    if max_label_lines is not None:
        if isinstance(max_label_lines, bool) or not isinstance(max_label_lines, numbers.Integral):
            raise TypeError(f"max_label_lines must be an int or None, got {max_label_lines!r}")
        if max_label_lines < 0:
            raise ValueError(f"max_label_lines must be >= 0, got {max_label_lines!r}")
        max_label_lines = int(max_label_lines)
    if not (
        max_label_width is None or max_label_width == "auto" or isinstance(max_label_width, (int, float))
    ):
        raise ValueError(f"max_label_width must be a number, 'auto' or None, got {max_label_width!r}")

    if label_colors not in (True, False, "auto"):
        raise ValueError(f"label_colors must be True, False or 'auto', got {label_colors!r}")
    if hierarchy is True:
        hierarchy = "shadow"
    elif hierarchy is False:
        hierarchy = None
    if hierarchy is not None and hierarchy not in HIERARCHY_MODES:
        raise ValueError(f"hierarchy must be True, False, None, 'shadow' or 'outline', got {hierarchy!r}")

    own_figure = ax is None
    W, H = float(geometry.width), float(geometry.height)
    if own_figure:
        # Sized by content (see _figure_width/_figure_height); the width is set once the labels are measured.
        fig = plt.figure(figsize=(_figure_width(geometry, 0.0), _figure_height(geometry)))
        ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    assert ax is not None

    artists = AlluvialArtists(geometry)
    colors = _Colors(
        _resolve_palette(palette, geometry),
        _palette.DEFAULT_HIGHLIGHT_COLOR if default_color is None else default_color,
    )
    net_ids = [n.id for n in geometry.networks]

    s_kw = dict(streamline_kw or {})
    alpha = s_kw.pop("alpha", streamline_alpha)
    n_lines = max(len(geometry.streamlines), 1)
    for k, s in enumerate(geometry.streamlines):
        z = Z_STREAMLINE + k / (n_lines + 1)
        left = colors(s.left_highlight_index, s.left_insignificant)
        right = colors(s.right_highlight_index, s.right_insignificant)
        points = s.path()
        if not gradient or left == right or s.x1 <= s.x0:
            kw = {"facecolor": left, "edgecolor": "none", "linewidth": 0, "alpha": alpha, "zorder": z}
            artist: Artist = _streamline_patch(points, H, **{**kw, "rasterized": rasterized, **s_kw})
            ax.add_patch(artist)
        else:
            clip = _streamline_patch(points, H, facecolor="none", edgecolor="none", transform=ax.transData)
            ys = [H - y for _, (_, y) in points]
            # interpolation="none" embeds the 256 x 1 strip as is in PDF/SVG (resampling would embed a
            # bbox-sized raster per streamline).
            artist = ax.imshow(
                _gradient(left, right),
                extent=(s.x0, s.x1, min(ys), max(ys)),
                aspect="auto",
                interpolation="none",
                alpha=alpha,
                zorder=z,
                rasterized=rasterized,
            )
            artist.set_clip_path(clip)
            img_kw = {
                k: v for k, v in s_kw.items() if k not in ("facecolor", "color", "edgecolor", "linewidth")
            }
            if img_kw:
                artist.set(**img_kw)
        artist.set_gid(f"streamline:{s.id}")
        artists.streamlines.append(artist)

    m_kw = {"edgecolor": edgecolor, "linewidth": linewidth, "zorder": Z_MODULE, "rasterized": rasterized}
    m_kw.update(module_kw or {})
    for network in geometry.networks:
        for module in network.modules:
            for gi, g in enumerate(module.groups):
                kw = {"facecolor": colors(g.highlight_index, g.insignificant), **m_kw}
                if isinstance(kw["edgecolor"], str) and kw["edgecolor"] == "face":
                    kw["edgecolor"] = kw["facecolor"]
                rect = Rectangle((g.x, H - g.y - g.height), g.width, g.height, **kw)
                rect.set_gid(f"module:{network.id}:{module.id}:{gi}")
                ax.add_patch(rect)
                artists.modules.append(rect)
    colors.warn()
    artists._colors = colors  # for alluvial.legend

    # Per network: data px the hierarchy boxes stick out left, right, below and above the network's rect.
    net_ext = {n.index: [0.0, 0.0, 0.0, 0.0] for n in geometry.networks}
    if hierarchy is not None:
        h_kw = {"rasterized": rasterized, **(hierarchy_kw or {})}
        for network in geometry.networks:
            ext = net_ext[network.index]
            for outline in sorted(network.outlines, key=lambda o: o.order):
                depth = outline.max_level - outline.level
                x, y, w, h = outline.x, H - outline.y - outline.height, outline.width, outline.height
                if hierarchy == "shadow":
                    d = SHADOW_OFFSET * depth
                    x, y = x + d, y - d
                    kw = {"facecolor": SHADOW_COLOR, "edgecolor": "none", "zorder": Z_SHADOW, **h_kw}
                    patch: Patch = Rectangle((x, y), w, h, **kw)
                else:
                    d = 1 + 2.5 * depth
                    x, y, w, h = x - d, y - d, w + 2 * d, h + 2 * d
                    kw = {
                        "fill": False,
                        "edgecolor": OUTLINE_COLOR,
                        "linewidth": OUTLINE_LINEWIDTH,
                        "linestyle": "-",
                        "joinstyle": "round",
                        "zorder": Z_MODULE - 0.5 / (n_lines + 1),
                        **h_kw,
                    }
                    patch = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={d}", **kw)
                ext[0] = max(ext[0], network.x - x)
                ext[1] = max(ext[1], x + w - network.x - network.width)
                ext[2] = max(ext[2], -y)
                ext[3] = max(ext[3], y + h - H)
                patch.set_gid(f"outline:{network.id}:{outline.path}")
                ax.add_patch(patch)
                artists.outlines.append(patch)

    base = {"zorder": Z_TEXT, "clip_on": False, **(text_kw or {})}
    blocks: list[_Block] = []
    if module_labels:
        fs = _fontsize_pt(fontsize, "small")
        l_kw = {"parse_math": False, **base, **(label_kw or {})}
        for network in geometry.networks:
            for module in network.modules:
                label = module.label
                if label is None:
                    continue
                # a custom module name replaces the leaf names (TS `module.name || <LargestLeafNames>`), in black
                names = (
                    [module.name]
                    if module.name
                    else list(module.name_candidates or module.largest_leaf_names) or label.text.split("\n")
                )
                if max_label_lines is not None:
                    names = names[:max_label_lines]
                if not names:
                    continue
                side = 1 if label.anchor == "start" else -1
                ext = net_ext.get(module.network_index, [0.0] * 4)
                x = module.x + module.width + ext[1] if side > 0 else module.x - ext[0]
                texts = []
                his = module.name_highlight_indices
                color_lines = (
                    label_colors is True or (label_colors == "auto" and bool(geometry.highlight_labels))
                ) and not ({"color", "c"} & set(l_kw))
                for k, name in enumerate(names):
                    line_kw = dict(l_kw)
                    if color_lines and not module.name and k < len(his):
                        insignificant = k < len(module.name_insignificant) and module.name_insignificant[k]
                        line_kw["color"] = colors.text(his[k], insignificant)
                    t = ax.text(
                        x,
                        H - label.y,
                        name,
                        ha="left" if side > 0 else "right",
                        va="baseline",
                        fontsize=fs,
                        **line_kw,
                    )
                    t.set_in_layout(False)
                    t.set_gid(f"module-label:{net_ids[module.network_index]}:{module.id}:{k}")
                    texts.append(t)
                artists.module_labels.extend(texts)
                blocks.append(
                    _Block(module, side, names, texts, x, H - label.y, fs, 0.5 * _x_height(texts[0]))
                )

    names_: list[tuple[Text, float, str]] = []
    if network_labels:
        nfs = _fontsize_pt(network_fontsize, "medium")
        n_kw = {**base, **(network_label_kw or {})}
        for network in geometry.networks:
            nl = network.name_label
            if not nl.text:
                continue
            x = network.x + network.width / 2
            t = ax.text(x, 0.0, nl.text, ha="center", va="top", fontsize=nfs, **n_kw)
            t.set_in_layout(False)
            t.set_gid(f"network-label:{network.id}")
            artists.network_labels.append(t)
            names_.append((t, x, nl.text))

    ax.set_axis_off()
    fitter = _Fitter(
        ax,
        geometry,
        artists,
        blocks,
        names_,
        label_pad=label_pad,
        max_label_width=max_label_width,
        avoid_label_overlap=avoid_label_overlap,
    )
    if geometry.networks:
        first, last = geometry.networks[0].index, geometry.networks[-1].index
        fitter.extents = (
            net_ext[first][0],
            net_ext[last][1],
            max(e[2] for e in net_ext.values()),
            max(e[3] for e in net_ext.values()),
        )
    ax.add_artist(fitter)
    if legend:
        _add_legend(ax, fitter)
    renderer = ax.figure._get_renderer()
    if own_figure:
        # Label space: the width the untruncated labels and hierarchy boxes add at one layout px per point.
        x0, x1, _, _ = fitter.fit(renderer, native=True)
        name_pt = max(
            (_measure(t, s, renderer)[0] + 0.5 * t.get_fontsize() + PAD_PT for t, _, s in names_), default=0.0
        )
        ax.figure.set_size_inches(_figure_width(geometry, x1 - x0 - W, name_pt), _figure_height(geometry))
    fitter.fit(renderer)
    if fitter.overflow:
        warnings.warn(
            "the labels leave almost no room for the diagram in this axes; use a larger axes, a smaller "
            "fontsize, max_label_width or max_label_lines",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
    return ax


def legend(ax: Axes, *, other: str | None = None, **kwargs: Any) -> Legend | None:
    """Add a legend of the highlight labels (``layout(highlight=...)``) of the diagram drawn on ``ax``.

    By default the legend is a row of color swatches centered above the diagram, inside the axes. It takes more rows
    when it is wider than the axes, and the fit makes room for it at every draw. Passing ``loc`` or
    ``bbox_to_anchor`` places it like any matplotlib legend instead (no room is made). Calling it again replaces
    the legend.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        An axes ``draw`` or ``plot`` drew on.
    other : str, optional
        Also add an entry in the default (gray) color with this label, e.g. ``"other"``.
    **kwargs
        ``Axes.legend`` keywords (e.g. ``title``, ``fontsize``, ``ncols``, ``frameon``).

    Returns
    -------
    matplotlib.legend.Legend or None
        None (with a warning) if the geometry has no highlight labels and no ``other``.

    Examples
    --------
    >>> import alluvial
    >>> networks = [{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}]
    >>> ax = alluvial.plot(networks, highlight={"group a": ["a"]})
    >>> legend = alluvial.legend(ax, other="other", title="Nodes")
    >>> [text.get_text() for text in legend.get_texts()]
    ['group a', 'other']
    """
    return _add_legend(ax, _fitter(ax), other=other, **kwargs)


def _add_legend(ax: Axes, fitter: _Fitter, *, other: str | None = None, **kwargs: Any) -> Legend | None:
    art = fitter.artists
    colors: _Colors = art._colors
    entries = [
        (h.label, colors(h.highlight_index)) for h in art.geometry.highlight_labels if h.highlight_index >= 0
    ]
    if other is not None:
        entries.append((other, colors(_palette.NOT_HIGHLIGHTED)))
    if art.legend is not None:
        art.legend.remove()
        art.legend = None
        fitter.set_legend(None)
    if not entries:
        warnings.warn(
            "no highlight labels to show in a legend: every label is drawn in the default (gray) color; pass "
            "other='...' for a gray entry"
            if art.geometry.highlight_labels
            else "no highlight labels to show in a legend; use layout(..., highlight=...)",
            UserWarning,
            stacklevel=user_stacklevel(),
        )
        return None
    handles = [Patch(facecolor=c, edgecolor="none", label=label) for label, c in entries]
    managed = "loc" not in kwargs and "bbox_to_anchor" not in kwargs
    opts: dict[str, Any] = {
        "frameon": False,
        "fontsize": "small",
        "handlelength": 0.8,
        "handleheight": 0.8,
        "handletextpad": 0.4,
        "columnspacing": 1.2,
        "borderpad": 0.0,
        "borderaxespad": 0.0,
    }
    opts.update(kwargs)
    fontsize = _fontsize_pt(opts["fontsize"], "small")
    if managed:
        opts["loc"] = "lower center"
        if "ncols" not in opts and "ncol" not in opts:
            opts["ncols"] = _legend_columns(
                [label for label, _ in entries], fontsize, opts, fitter.axes_size_pt()[0]
            )
    leg = ax.legend(handles=handles, **opts)
    art.legend = leg
    if managed:
        leg.set_in_layout(False)
        fitter.set_legend(leg, LEGEND_GAP_EM * fontsize)
    return leg


def _legend_columns(labels: list[str], fontsize: float, opts: dict[str, Any], width_pt: float) -> int:
    """The most columns (column-major, as ``Axes.legend`` fills them) whose row fits in ``width_pt``."""
    prop = FontProperties(size=fontsize)
    entry = [
        text_to_path.get_text_width_height_descent(label, prop, ismath=False)[0]
        + (opts["handlelength"] + opts["handletextpad"]) * fontsize
        for label in labels
    ]
    n = len(entry)
    for k in range(n, 1, -1):
        rows = math.ceil(n / k)
        cols = [max(entry[j * rows : (j + 1) * rows], default=0.0) for j in range(k)]
        if sum(cols) + (k - 1) * opts["columnspacing"] * fontsize <= width_pt - 2 * PAD_PT:
            return k
    return 1


_DRAW_KWARGS = frozenset(p for p in inspect.signature(draw).parameters if p not in ("geometry", "ax"))


def plot(networks: Iterable[Any], ax: Axes | None = None, **kwargs: Any) -> Axes:
    """Lay out and draw in one call: ``draw(layout(networks, **layout_kwargs), ax, **draw_kwargs)``.

    Parameters
    ----------
    networks : iterable of str or PathLike, infomap.Infomap, dict or NetworkFile, or a pandas DataFrame
        Networks from left to right, as for ``alluvial.layout``: paths, run ``infomap.Infomap`` objects, Infomap
        JSON dicts, ``NetworkFile`` objects, dicts mapping nodes to modules (``alluvial.partition(...)``), or a
        long-format DataFrame with one network per ``network`` value (``alluvial.from_dataframe``).
    ax : matplotlib.axes.Axes, optional
        Target axes; by default a new figure sized by content (see ``alluvial.draw``): taller with more modules,
        wider with more networks and longer labels.
    **kwargs
        Keyword arguments of ``alluvial.layout`` (including ``LayoutOptions`` fields) and ``alluvial.draw``.

    Returns
    -------
    matplotlib.axes.Axes
        ``get_artists(ax)`` returns the created artists.

    Examples
    --------
    >>> import alluvial
    >>> ax = alluvial.plot([{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], names=["2020", "2021"])

    Layout and drawing keywords go together, here on an axes of your own:

    >>> import matplotlib.pyplot as plt
    >>> fig, ax = plt.subplots(figsize=(3.4, 2.4), layout="constrained")
    >>> ax = alluvial.plot(
    ...     [{"a": 1, "b": 1, "c": 2}, {"a": 1, "b": 2, "c": 2}], ax=ax, colors="similarity", palette="tab10"
    ... )
    """
    from .layout import LAYOUT_KEYWORDS, LayoutOptions, layout

    layout_names = {*LAYOUT_KEYWORDS, *LayoutOptions.field_names()}
    unknown = sorted(set(kwargs) - layout_names - _DRAW_KWARGS)
    if unknown:
        import difflib

        hints = []
        for k in unknown:
            close = difflib.get_close_matches(k, sorted(layout_names | _DRAW_KWARGS), n=1)
            hints.append(f"{k!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
        raise TypeError(
            f"plot() got unexpected keyword argument(s) {', '.join(hints)}; it takes the keywords of "
            "alluvial.layout and alluvial.draw"
        )
    draw_kwargs = {k: v for k, v in kwargs.items() if k in _DRAW_KWARGS}
    layout_kwargs = {k: v for k, v in kwargs.items() if k not in _DRAW_KWARGS}
    return draw(layout(networks, **layout_kwargs), ax, **draw_kwargs)
