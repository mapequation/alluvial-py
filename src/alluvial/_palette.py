"""Color data and color functions of the web app.

- ``C3_SINEBOW``: the default 512-color scheme ``"C3 Sinebow"`` (``schemes/index.ts``) in c3's default tone,
  verbatim TS strings.
- ``SCHEMES``/``SCHEME_GROUPS``/``get_scheme``: the 65 named color schemes of the web app (``COLOR_SCHEMES``,
  ``SCHEME_GROUPS``), dumped verbatim from TS (docs/dev/port-notes/v3-webapp-json.md §6).
- ``TONES``/``DEFAULT_TONE``/``scheme_colors``/``scheme_is_hue_source``/``default_scheme_offset``/
  ``hierarchy_options``: the c3 tone and offset of the C3 schemes and of coloring by module hierarchy
  (``schemes/index.ts``, web app 1.16), computed with ``c3-colors`` (the Python port of ``@mapequation/c3``, the
  same version as the TS lockfile).
- ``brighter``: an exact port of ``d3.hsl(color).brighter(k).toString()`` (d3-color 3.1.0).
- ``make_fill``: ``utils/highlight-color.ts``, the fill used for groups and streamline gradient stops.

Spec: docs/dev/port-notes/colors-render.md §2.3, §2.4, §3 and §8. No matplotlib import.
"""

from __future__ import annotations

import functools
import json
import math
import numbers
import re
from collections.abc import Callable, Mapping, Sequence
from importlib import resources
from types import MappingProxyType
from typing import Any

from ._jscompat import js_round

__all__ = [
    "BRIGHTER",
    "C3_SINEBOW",
    "DEFAULT_HIGHLIGHT_COLOR",
    "DEFAULT_TONE",
    "INSIGNIFICANT_BRIGHTER_K",
    "NOT_HIGHLIGHTED",
    "SCHEMES",
    "SCHEME_GROUPS",
    "TONES",
    "brighter",
    "default_scheme_offset",
    "get_scheme",
    "hierarchy_options",
    "hsl_to_rgb",
    "make_fill",
    "parse_color",
    "rgb_to_hsl",
    "scheme_colors",
    "scheme_is_hue_source",
    "to_rgb01",
]

DEFAULT_HIGHLIGHT_COLOR = "#b6b69f"
NOT_HIGHLIGHTED = -1
INSIGNIFICANT_BRIGHTER_K = 0.8
BRIGHTER = 1 / 0.7


def _load_schemes() -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    text = resources.files("alluvial").joinpath("data", "color-schemes.json").read_text(encoding="utf-8")
    data = json.loads(text)
    schemes = {name: tuple(data["schemes"][name]) for name in data["names"]}
    groups = {group: tuple(names) for group, names in data["groups"].items()}
    return schemes, groups


_SCHEMES, _GROUPS = _load_schemes()

#: The web app's named color schemes (TS ``COLOR_SCHEMES``, in its key order): name -> color strings, verbatim
#: (hex or ``"rgb(r, g, b)"``). The default is ``"C3 Sinebow"``.
SCHEMES: Mapping[str, tuple[str, ...]] = MappingProxyType(_SCHEMES)
#: The scheme groups of the web app's scheme menu (TS ``SCHEME_GROUPS``): group -> scheme names.
SCHEME_GROUPS: Mapping[str, tuple[str, ...]] = MappingProxyType(_GROUPS)
#: The default scheme ``"C3 Sinebow"`` in c3's default tone (512 colors).
C3_SINEBOW: tuple[str, ...] = _SCHEMES["C3 Sinebow"]

# --- c3 tone and offset (TS schemes/index.ts) ------------------------------------------------------------------

#: Where the C3 schemes take their hues from (TS ``C3_HUES``): ``"Oklch"`` or a d3 interpolator name suffix.
C3_HUES: Mapping[str, str] = MappingProxyType(
    {
        "C3 Oklch": "Oklch",
        "C3 Turbo": "Turbo",
        "C3 Rainbow": "Rainbow",
        "C3 Sinebow": "Sinebow",
        "C3 Viridis": "Viridis",
    }
)

#: c3's default tone, of the C3 schemes in ``SCHEMES`` (TS ``DEFAULT_TONE``).
DEFAULT_TONE = "strong"


def _c3_tones() -> tuple[str, ...]:
    import c3

    return tuple(c3.tones)


#: The c3 tones, which set the lightness and chroma of the C3 schemes and of coloring by module hierarchy (TS
#: ``TONES``, c3's ``Object.keys(tones)``).
TONES: tuple[str, ...] = _c3_tones()


def _c3_hue(hue: str) -> Any:
    """A ``C3_HUES`` value as a c3 hue source: ``"Oklch"``, else the d3 interpolator (as TS c3's ``getScheme``)."""
    if hue == "Oklch":
        return hue
    from ._d3_interpolators import interpolator

    return interpolator(f"interpolate{hue}")


@functools.lru_cache(maxsize=64)
def _c3_scheme(name: str, tone: str, offset: float | None) -> tuple[str, ...]:
    """TS ``c3Scheme``: ``palette(512, { hue: C3_HUES[name], tone, offset: offset ?? undefined })``."""
    import c3

    return tuple(c3.palette(512, hue=_c3_hue(C3_HUES[name]), tone=tone, offset=offset))


def _interpolated() -> Mapping[str, str]:
    from ._d3_interpolators import scheme_interpolators

    return scheme_interpolators()


def check_tone(tone: Any) -> str:
    """``tone`` if it is one of ``TONES``, else ``ValueError``."""
    if not isinstance(tone, str) or tone not in TONES:
        raise ValueError(f"unknown c3 tone {tone!r}; the tones are {', '.join(TONES)}")
    return tone


def check_offset(offset: Any) -> float | None:
    """``offset`` if it is ``None`` (c3's default) or a finite real number, else ``TypeError``/``ValueError``."""
    if offset is None:
        return None
    if isinstance(offset, bool) or not isinstance(offset, numbers.Real):
        raise TypeError(f"offset must be a number of degrees or None, got {offset!r}")
    if not math.isfinite(offset):
        raise ValueError(f"offset must be finite, got {offset!r}")
    return offset


def scheme_colors(name: str, tone: str = DEFAULT_TONE, offset: float | None = None) -> tuple[str, ...]:
    """The colors of a named scheme (TS ``schemeColors``): the C3 schemes depend on the c3 ``tone`` and ``offset``
    (degrees around the hue source; ``None`` for c3's default), the other schemes do not.

    Raises
    ------
    ValueError
        For an unknown scheme or tone.
    """
    scheme = get_scheme(name)
    check_tone(tone)
    offset = check_offset(offset)
    if name not in C3_HUES or (tone == DEFAULT_TONE and offset is None):
        return scheme
    return _c3_scheme(name, tone, offset)


def scheme_is_hue_source(name: str) -> bool:
    """Whether c3 takes the scheme as a hue source (TS ``schemeIsHueSource``): the C3 and the interpolated schemes,
    whose colors or hierarchy coloring the tone and offset change."""
    return name in C3_HUES or name in _interpolated()


def default_scheme_offset(name: str) -> float:
    """Where c3 puts the first color by default, in degrees around the hue source (TS ``defaultSchemeOffset``):
    245 on the OKLCH hue circle (``"C3 Oklch"``), else 0 at the start of a scheme."""
    return 245 if C3_HUES.get(name) == "Oklch" else 0


def hierarchy_options(name: str, tone: str = DEFAULT_TONE, offset: float | None = None) -> dict[str, Any]:
    """Keyword arguments for c3's ``hierarchy()`` that make top modules follow a scheme (TS ``hierarchyOptions``).

    The C3 and interpolated schemes are hue sources in the tone and offset; the other schemes are lists of colors,
    which c3 takes as seeds (and infers the tone from).
    """
    if name in C3_HUES:
        return {"hue": _c3_hue(C3_HUES[name]), "tone": tone, "offset": offset}
    interpolated = _interpolated()
    if name in interpolated:
        from ._d3_interpolators import interpolator

        return {"hue": interpolator(interpolated[name]), "tone": tone, "offset": offset}
    return {"seeds": get_scheme(name)}


def get_scheme(name: str) -> tuple[str, ...]:
    """The colors of a named web-app scheme (``SCHEMES[name]``).

    Raises
    ------
    ValueError
        For an unknown name, listing close matches.
    """
    if not isinstance(name, str):
        raise TypeError(f"scheme must be a scheme name (str), got {type(name).__name__}")
    scheme = _SCHEMES.get(name)
    if scheme is None:
        import difflib

        lower = {n.lower(): n for n in _SCHEMES}
        close = [lower[n] for n in difflib.get_close_matches(name.lower(), list(lower), n=3, cutoff=0.5)]
        hint = f"; did you mean {', '.join(map(repr, close))}?" if close else ""
        raise ValueError(f"unknown color scheme {name!r}{hint} (alluvial.SCHEMES lists all {len(_SCHEMES)})")
    return scheme


_RGB_RE = re.compile(r"rgb\(\s*([+-]?[0-9]+)\s*,\s*([+-]?[0-9]+)\s*,\s*([+-]?[0-9]+)\s*\)")
_HEX_RE = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def parse_color(color: str) -> tuple[int, int, int]:
    """Parse ``"#rgb"``, ``"#rrggbb"`` or ``"rgb(r, g, b)"`` into 0-255 integer channels.

    Raises
    ------
    ValueError
        For any other color syntax (names, ``hsl()``, alpha forms).
    """
    c = color.strip()
    m = _HEX_RE.fullmatch(c)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    m = _RGB_RE.fullmatch(c)
    if m:
        r, g, b = (int(v) for v in m.groups())
        return r, g, b
    raise ValueError(f"unsupported color {color!r}: expected #rgb, #rrggbb or rgb(r, g, b)")


def to_rgb01(color: str) -> tuple[float, float, float]:
    """Channels of ``parse_color(color)`` scaled to [0, 1] (clamped), for matplotlib."""
    return tuple(min(max(v, 0), 255) / 255 for v in parse_color(color))  # type: ignore[return-value]


def rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    """d3 ``hslConvert``: 0-255 channels to ``(h, s, l)``; ``h`` is NaN for grays, ``s`` NaN for black/white."""
    r, g, b = r / 255, g / 255, b / 255
    mn, mx = min(r, g, b), max(r, g, b)
    h, s, l = math.nan, mx - mn, (mx + mn) / 2
    if s:
        if r == mx:
            h = (g - b) / s + (6 if g < b else 0)
        elif g == mx:
            h = (b - r) / s + 2
        else:
            h = (r - g) / s + 4
        s /= (mx + mn) if l < 0.5 else (2 - mx - mn)
        h *= 60
    else:
        s = 0.0 if 0 < l < 1 else h
    return h, s, l


def _hsl2rgb(h: float, m1: float, m2: float) -> float:
    if h < 60:
        v = m1 + (m2 - m1) * h / 60
    elif h < 180:
        v = m2
    elif h < 240:
        v = m1 + (m2 - m1) * (240 - h) / 60
    else:
        v = m1
    return v * 255


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    """d3 ``Hsl.rgb()``: unrounded, unclamped 0-255 channels."""
    if math.isnan(h):
        return (_hsl2rgb_nan(l),) * 3
    h = math.fmod(h, 360) + (360 if h < 0 else 0)
    if math.isnan(s):
        s = 0.0
    m2 = l + (l if l < 0.5 else 1 - l) * s
    m1 = 2 * l - m2
    return (
        _hsl2rgb(h - 240 if h >= 240 else h + 120, m1, m2),
        _hsl2rgb(h, m1, m2),
        _hsl2rgb(h + 240 if h < 120 else h - 120, m1, m2),
    )


def _hsl2rgb_nan(l: float) -> float:
    # s is 0 when h is NaN, so m1 = m2 = l; every comparison with NaN is false -> the m1 branch.
    m2 = l + (l if l < 0.5 else 1 - l) * 0.0
    m1 = 2 * l - m2
    return m1 * 255


def _clampi(v: float) -> int:
    if math.isnan(v):
        return 0
    return int(max(0.0, min(255.0, js_round(v))))


def brighter(color: str | None, k: float = INSIGNIFICANT_BRIGHTER_K) -> str:
    """Exact port of ``d3.hsl(color).brighter(k).toString()``.

    ``None`` (JS ``undefined``) gives ``"rgb(0, 0, 0)"`` as in d3.
    """
    if color is None:
        return "rgb(0, 0, 0)"
    h, s, l = rgb_to_hsl(*parse_color(color))
    r, g, b = hsl_to_rgb(h, s, l * BRIGHTER**k)
    return f"rgb({_clampi(r)}, {_clampi(g)}, {_clampi(b)})"


def make_fill(default: str, colors: Sequence[str]) -> Callable[[int, bool], str | None]:
    """Port of ``highlightColor(default, colors)``: ``fill(highlight_index, insignificant)``.

    Index -1 gives ``default``, an index inside ``colors`` gives that color, and any other index gives
    ``None`` (TS ``undefined``, drawn black by the browser). Insignificant groups use ``brighter(..., 0.8)``.
    """

    def fill(highlight_index: int, insignificant: bool = False) -> str | None:
        if highlight_index == NOT_HIGHLIGHTED:
            color: str | None = default
        elif 0 <= highlight_index < len(colors):
            color = colors[highlight_index]
        else:
            color = None
        if insignificant:
            return brighter(color, INSIGNIFICANT_BRIGHTER_K)
        return color

    return fill
