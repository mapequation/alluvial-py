"""Shared test infrastructure: fixture loading, the v1/v2 scenario split and a numeric deep compare.

Fixtures (``tests/fixtures/<group>__<variant>.json``) come from the real TS engine; the format is documented in
``tools/ts-fixtures/README.md``. They contain bare ``Infinity``/``-Infinity``/``NaN`` tokens, which ``json``
reads natively.

Test functions can request ``scenario`` (all), ``v1_scenario`` or ``v2_scenario`` to be parametrized over the
scenario names. Helper functions are importable with ``from conftest import ...``.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
DATA_DIR = TESTS_DIR / "data"

ALL_SCENARIOS: list[str] = sorted(p.stem for p in FIXTURES_DIR.glob("*.json"))

ABS_TOL = 1e-9


def fixture_path(name_or_path: str | os.PathLike[str]) -> Path:
    """Resolve a scenario name (``"planted-ftree__default"``) or a path to a fixture file."""
    p = Path(name_or_path)
    if p.suffix == ".json" and p.exists():
        return p
    return FIXTURES_DIR / f"{p.name.removesuffix('.json')}.json"


@cache
def _load_cached(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def load_fixture(name_or_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load a fixture as a fresh dict (each call returns a new object; the file text is cached)."""
    return json.loads(_load_cached(str(fixture_path(name_or_path))))


# v2: a fixture with a top-level ``features`` list (tools/ts-fixtures/README.md "v2 scenarios"); v1 has none.
V2_SCENARIOS: list[str] = [s for s in ALL_SCENARIOS if load_fixture(s).get("features")]
V1_SCENARIOS: list[str] = [s for s in ALL_SCENARIOS if s not in V2_SCENARIOS]


def fixture_data_paths(fx: dict[str, Any]) -> list[Path]:
    """Absolute paths of the input datasets of a fixture, in network order."""
    return [TESTS_DIR / p for p in fx["inputs"]["files"]]


# --- numeric deep compare -----------------------------------------------------------------------------------

_SVG_PATH_RE = re.compile(r"M[-+0-9.eE,MCLZInfinityNa]*Z")
_SVG_TOKEN_RE = re.compile(r"[MCLZ]|[-+]?(?:Infinity|NaN|(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?)|,")


@dataclass
class CompareResult:
    """Outcome of ``compare``: mismatches as ``(location, message)`` and float statistics."""

    mismatches: list[tuple[str, str]] = field(default_factory=list)
    floats_compared: int = 0
    non_bitwise: int = 0
    max_abs_diff: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def summary(self, limit: int = 20) -> str:
        lines = [
            f"{len(self.mismatches)} mismatches ({self.floats_compared} floats, {self.non_bitwise} not bitwise equal)"
        ]
        lines += [f"  {loc}: {msg}" for loc, msg in self.mismatches[:limit]]
        if len(self.mismatches) > limit:
            lines.append(f"  ... {len(self.mismatches) - limit} more")
        return "\n".join(lines)


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _compare_floats(a: float, b: float, loc: str, res: CompareResult, tol: float) -> None:
    res.floats_compared += 1
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        if not (math.isnan(a) and math.isnan(b)):
            res.mismatches.append((loc, f"{a!r} != {b!r}"))
            res.non_bitwise += 1
        return
    if a == b:
        return
    res.non_bitwise += 1
    diff = abs(a - b)
    if not math.isfinite(diff) or diff > tol:
        res.mismatches.append((loc, f"{a!r} != {b!r} (diff {diff:.3g})"))
    else:
        res.max_abs_diff = max(res.max_abs_diff, diff)


def _svg_tokens(s: str) -> list[str] | None:
    tokens = _SVG_TOKEN_RE.findall(s)
    return tokens if "".join(tokens) == s else None


def is_svg_path(s: Any) -> bool:
    return isinstance(s, str) and _SVG_PATH_RE.fullmatch(s) is not None


def _compare_svg(a: str, b: str, loc: str, res: CompareResult, tol: float) -> None:
    ta, tb = _svg_tokens(a), _svg_tokens(b)
    if ta is None or tb is None or len(ta) != len(tb):
        res.mismatches.append((loc, f"path structure differs: {a!r} != {b!r}"))
        return
    for i, (x, y) in enumerate(zip(ta, tb)):
        if x in "MCLZ," or y in "MCLZ,":
            if x != y:
                res.mismatches.append((f"{loc}[{i}]", f"path command {x!r} != {y!r}"))
                return
        else:
            _compare_floats(float(x), float(y), f"{loc}[{i}]", res, tol)


def _compare(a: Any, b: Any, loc: str, res: CompareResult, tol: float, ignore: frozenset[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        ka, kb = set(a) - ignore, set(b) - ignore
        for k in sorted(ka - kb, key=str):
            res.mismatches.append((f"{loc}.{k}", "unexpected key"))
        for k in sorted(kb - ka, key=str):
            res.mismatches.append((f"{loc}.{k}", "missing key"))
        for k in b:
            if k in ka:
                _compare(a[k], b[k], f"{loc}.{k}", res, tol, ignore)
        return
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            res.mismatches.append((loc, f"length {len(a)} != {len(b)}"))
        for i, (x, y) in enumerate(zip(a, b)):
            _compare(x, y, f"{loc}[{i}]", res, tol, ignore)
        return
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        if a is not b and not (isinstance(a, bool) and isinstance(b, bool) and a == b):
            res.mismatches.append((loc, f"{a!r} != {b!r}"))
        return
    if _is_num(a) and _is_num(b):
        if isinstance(a, int) and isinstance(b, int):
            if a != b:
                res.mismatches.append((loc, f"{a!r} != {b!r}"))
            return
        _compare_floats(a, b, loc, res, tol)
        return
    if isinstance(a, str) and isinstance(b, str):
        if a == b:
            if is_svg_path(b):
                res.floats_compared += sum(1 for t in _SVG_TOKEN_RE.findall(b) if t not in "MCLZ,")
            return
        if is_svg_path(a) and is_svg_path(b):
            _compare_svg(a, b, loc, res, tol)
        else:
            res.mismatches.append((loc, f"{a!r} != {b!r}"))
        return
    res.mismatches.append((loc, f"type {type(a).__name__} {a!r} != {type(b).__name__} {b!r}"))


def compare(
    actual: Any,
    expected: Any,
    *,
    tol: float = ABS_TOL,
    ignore: set[str] | frozenset[str] = frozenset(),
    root: str = "$",
) -> CompareResult:
    """Deep-compare ``actual`` against ``expected`` (fixture JSON).

    Dicts must have the same keys (except ``ignore``), sequences the same length and order. Ints, strings, bools
    and None compare exactly; a float on either side compares numerically with ``abs <= tol``; SVG path strings
    compare token by token (commands exactly, numbers with ``tol``). ``non_bitwise`` counts floats that are
    not exactly equal, even within tolerance.
    """
    res = CompareResult()
    _compare(actual, expected, root, res, tol, frozenset(ignore))
    return res


def assert_matches(actual: Any, expected: Any, **kwargs: Any) -> CompareResult:
    """``compare`` and raise ``AssertionError`` with a summary on any mismatch. Returns the result."""
    res = compare(actual, expected, **kwargs)
    if not res.ok:
        raise AssertionError(res.summary())
    return res


# --- pytest hooks and fixtures -----------------------------------------------------------------------------


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    for argname, names in (
        ("scenario", ALL_SCENARIOS),
        ("v1_scenario", V1_SCENARIOS),
        ("v2_scenario", V2_SCENARIOS),
    ):
        if argname in metafunc.fixturenames:
            metafunc.parametrize(argname, names)


@pytest.fixture
def fixture_loader():
    """The ``load_fixture(name_or_path) -> dict`` function."""
    return load_fixture


@pytest.fixture
def deep_compare():
    """The ``assert_matches(actual, expected, **kw) -> CompareResult`` function."""
    return assert_matches
