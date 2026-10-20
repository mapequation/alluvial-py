"""The d3 interpolators the web app hands to c3 as hue sources (d3-scale-chromatic 3.1, d3-interpolate 3.0.1,
d3-color 3.1), returning the same strings as d3 (``"rgb(r, g, b)"``, or ``"#rrggbb"`` for the viridis ramps).

TS ``schemes/index.ts`` (``INTERPOLATED``) samples them for the interpolated schemes and passes them to c3's
``hierarchy()`` as the hue of those schemes; ``"C3 Viridis"`` takes its hue from ``interpolateViridis``. The colour
data (the ColorBrewer ramps and the viridis ramps) is dumped from the TS repo's d3 into
``data/d3-interpolators.json`` (tools/ts-fixtures ``--make-data``). No matplotlib import.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from functools import cache
from importlib import resources

from ._jscompat import js_round

Interpolator = Callable[[float], str]


def _clampi(value: float) -> int:
    """d3-color ``clampi``: ``Math.max(0, Math.min(255, Math.round(value) || 0))``."""
    r = js_round(value)
    if math.isnan(r) or r == 0:
        return 0
    return int(max(0.0, min(255.0, r)))


def _format_rgb(r: float, g: float, b: float) -> str:
    """d3-color ``rgb.formatRgb()`` of an opaque colour."""
    return f"rgb({_clampi(r)}, {_clampi(g)}, {_clampi(b)})"


def _hex_rgb(color: str) -> tuple[int, int, int]:
    n = int(color[1:], 16)
    return (n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF


# --- d3-interpolate basis + rgbBasis (the ColorBrewer ramps: ramp(scheme) = interpolateRgbBasis(scheme[last]))


def _basis(t1: float, v0: float, v1: float, v2: float, v3: float) -> float:
    t2 = t1 * t1
    t3 = t2 * t1
    return (
        (1 - 3 * t1 + 3 * t2 - t3) * v0
        + (4 - 6 * t2 + 3 * t3) * v1
        + (1 + 3 * t1 + 3 * t2 - 3 * t3) * v2
        + t3 * v3
    ) / 6


def _basis_spline(values: Sequence[float]) -> Callable[[float], float]:
    n = len(values) - 1

    def spline(t: float) -> float:
        if t <= 0:
            t = 0
            i = 0
        elif t >= 1:
            t = 1
            i = n - 1
        else:
            i = math.floor(t * n)
        v1 = values[i]
        v2 = values[i + 1]
        v0 = values[i - 1] if i > 0 else 2 * v1 - v2
        v3 = values[i + 2] if i < n - 1 else 2 * v2 - v1
        return _basis((t - i / n) * n, v0, v1, v2, v3)

    return spline


def _rgb_basis(colors: Sequence[str]) -> Interpolator:
    channels = [_hex_rgb(c) for c in colors]
    r, g, b = (_basis_spline([float(c[k]) for c in channels]) for k in range(3))
    return lambda t: _format_rgb(r(t), g(t), b(t))


# --- d3-scale-chromatic ramp (viridis, magma, inferno, plasma)


def _ramp(colors: Sequence[str]) -> Interpolator:
    n = len(colors)
    return lambda t: colors[max(0, min(n - 1, math.floor(t * n)))]


# --- d3-color cubehelix + d3-interpolate cubehelixLong

_A = -0.14861
_B = +1.78277
_C = -0.29227
_D = -0.90649
_E = +1.97294
_RADIANS = math.pi / 180


def _cubehelix_rgb(h: float, s: float, lum: float) -> tuple[float, float, float]:
    """d3-color ``Cubehelix.rgb()`` of ``cubehelix(h, s, l)`` (unrounded channels)."""
    h = 0 if math.isnan(h) else (h + 120) * _RADIANS
    a = 0 if math.isnan(s) else s * lum * (1 - lum)
    cosh = math.cos(h)
    sinh = math.sin(h)
    return (
        255 * (lum + a * (_A * cosh + _B * sinh)),
        255 * (lum + a * (_C * cosh + _D * sinh)),
        255 * (lum + a * (_E * cosh)),
    )


def _nogamma(a: float, b: float) -> Callable[[float], float]:
    d = b - a
    if d:
        return lambda t: a + t * d
    value = b if math.isnan(a) else a
    return lambda t: value


def _cubehelix_long(start: tuple[float, float, float], end: tuple[float, float, float]) -> Interpolator:
    """``interpolateCubehelixLong(start, end)`` (gamma 1: ``l(t ** 1)``)."""
    h = _nogamma(start[0], end[0])
    s = _nogamma(start[1], end[1])
    lum = _nogamma(start[2], end[2])
    return lambda t: _format_rgb(*_cubehelix_rgb(h(t), s(t), lum(t**1.0)))


# --- formulas


def _cividis(t: float) -> str:
    t = max(0.0, min(1.0, t))
    return f"rgb({_clamp_round(-4.54 - t * (35.34 - t * (2381.73 - t * (6402.7 - t * (7024.72 - t * 2710.57)))))}, {_clamp_round(32.49 + t * (170.73 + t * (52.82 - t * (131.46 - t * (176.58 - t * 67.37)))))}, {_clamp_round(81.24 + t * (442.36 - t * (2482.43 - t * (6167.24 - t * (6614.94 - t * 2475.67)))))})"


def _turbo(t: float) -> str:
    t = max(0.0, min(1.0, t))
    return f"rgb({_clamp_round(34.61 + t * (1172.33 - t * (10793.56 - t * (33300.12 - t * (38394.49 - t * 14825.05)))))}, {_clamp_round(23.31 + t * (557.33 + t * (1225.33 - t * (3574.96 - t * (1073.77 + t * 707.56)))))}, {_clamp_round(27.2 + t * (3211.1 - t * (15327.97 - t * (27814 - t * (22569.18 - t * 6838.66)))))})"


def _clamp_round(value: float) -> int:
    """``Math.max(0, Math.min(255, Math.round(value)))`` (no NaN guard; the formulas are finite)."""
    return int(max(0.0, min(255.0, js_round(value))))


def _rainbow(t: float) -> str:
    if t < 0 or t > 1:
        t -= math.floor(t)
    ts = abs(t - 0.5)
    return _format_rgb(*_cubehelix_rgb(360 * t - 100, 1.5 - 1.5 * ts, 0.8 - 0.9 * ts))


_PI_1_3 = math.pi / 3
_PI_2_3 = math.pi * 2 / 3


def _sinebow(t: float) -> str:
    t = (0.5 - t) * math.pi
    x = math.sin(t)
    r = 255 * x * x
    x = math.sin(t + _PI_1_3)
    g = 255 * x * x
    x = math.sin(t + _PI_2_3)
    b = 255 * x * x
    return _format_rgb(r, g, b)


_FORMULAS: dict[str, Interpolator] = {
    "interpolateCividis": _cividis,
    "interpolateTurbo": _turbo,
    "interpolateRainbow": _rainbow,
    "interpolateSinebow": _sinebow,
    "interpolateCubehelixDefault": _cubehelix_long((300, 0.5, 0.0), (-240, 0.5, 1.0)),
    "interpolateWarm": _cubehelix_long((-100, 0.75, 0.35), (80, 1.50, 0.8)),
    "interpolateCool": _cubehelix_long((260, 0.75, 0.35), (80, 1.50, 0.8)),
}


@cache
def _data() -> dict:
    text = resources.files("alluvial").joinpath("data", "d3-interpolators.json").read_text(encoding="utf-8")
    return json.loads(text)


@cache
def interpolator(name: str) -> Interpolator:
    """The d3 interpolator ``name`` (``"interpolateBrBG"``, ``"interpolateViridis"``, ...)."""
    entry = _data()["interpolators"].get(name)
    if entry is None:
        raise ValueError(f"unknown d3 interpolator {name!r}")
    if entry["kind"] == "basis":
        return _rgb_basis(entry["colors"])
    if entry["kind"] == "ramp":
        return _ramp(tuple(entry["colors"]))
    return _FORMULAS[name]


def scheme_interpolators() -> dict[str, str]:
    """The web app's interpolated schemes (TS ``INTERPOLATED``): scheme name -> d3 interpolator name."""
    return dict(_data()["schemes"])
