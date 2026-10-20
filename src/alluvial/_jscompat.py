"""JavaScript number, arithmetic and ordering semantics needed for bit-exact parity with the TS engine.

See docs/dev/port-notes: streamlines.md §7 (Number#toString), parsers.md §5 and §12 (Number(string),
identifier strings), model.md §0, §7.5 and §12 (left-to-right sums, own-key order, identity search),
colors-render.md §10 (Math.round, NaN-propagating min/max).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

T = TypeVar("T")

NAN = float("nan")

__all__ = [
    "NAN",
    "index_of_identity",
    "is_array_index_key",
    "js_array_join",
    "js_clamp",
    "js_divide",
    "js_is_integer",
    "js_json_stringify",
    "js_max",
    "js_min",
    "js_num_str",
    "js_number",
    "js_number_to_string",
    "js_own_keys_order",
    "js_round",
    "js_sum",
    "js_truthy",
    "stable_sort",
]


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def js_number_to_string(x: float) -> str:
    """Format a number exactly like ECMAScript ``Number.prototype.toString()`` (radix 10).

    Integral values print without ``.0``, and the exponent form is ``1e-7`` / ``1e+21``.
    """
    if not _is_number(x):
        raise TypeError(f"expected a number, got {type(x).__name__}")
    x = float(x)
    if math.isnan(x):
        return "NaN"
    if x == 0:
        return "0"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    sign = "-" if x < 0 else ""
    mant, _, exp = repr(abs(x)).partition("e")
    ip, _, fp = mant.partition(".")
    s = ip + fp
    z = len(s) - len(s.lstrip("0"))
    digits = s.lstrip("0").rstrip("0")
    k = len(digits)
    n = len(ip) + int(exp or 0) - z
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        out = digits[0] + ("." + digits[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + out


js_num_str = js_number_to_string

# ECMAScript StrWhiteSpaceChar: WhiteSpace (incl. every Zs) and LineTerminator. Python's str.strip()
# also strips \x1c-\x1f and \x85, which JS keeps.
_JS_WS = "\t\n\v\f\r                  　﻿"
_DECIMAL_RE = re.compile(r"[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_RADIX_RE = re.compile(r"0(?:([xX])([0-9a-fA-F]+)|([oO])([0-7]+)|([bB])([01]+))")


def js_number(value: Any) -> float:
    """Convert like JS ``Number(value)`` for strings, numbers, ``None`` (undefined) and bools.

    ``""`` and whitespace give 0, ``0x``/``0o``/``0b`` prefixes are accepted (unsigned only),
    ``Infinity`` is accepted, and anything else that is not a decimal literal gives NaN.
    """
    if value is None:
        return NAN
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if _is_number(value):
        return float(value)
    if not isinstance(value, str):
        return NAN
    s = value.strip(_JS_WS)
    if s == "":
        return 0.0
    if s in ("Infinity", "+Infinity"):
        return math.inf
    if s == "-Infinity":
        return -math.inf
    if _DECIMAL_RE.fullmatch(s):
        return float(s)
    m = _RADIX_RE.fullmatch(s)
    if m:
        if m.group(2) is not None:
            return float(int(m.group(2), 16))
        if m.group(4) is not None:
            return float(int(m.group(4), 8))
        return float(int(m.group(6), 2))
    return NAN


def js_sum(values: Iterable[float]) -> float:
    """Left-to-right float sum from 0, like ``xs.reduce((a, b) => a + b, 0)``.

    Never use the builtin ``sum`` for engine values: since Python 3.12 it is compensated.
    """
    total = 0.0
    for v in values:
        total = total + v
    return total


def js_divide(a: float, b: float) -> float:
    """IEEE-754 division as in JS: ``x/0`` is ``±Infinity`` and ``0/0`` is NaN instead of raising."""
    if b == 0:
        if a == 0 or math.isnan(a):
            return NAN
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def js_max(*values: float) -> float:
    """``Math.max``: NaN in any position propagates, and ``+0`` is larger than ``-0``."""
    result = -math.inf
    for v in values:
        if math.isnan(v):
            return NAN
        if v > result or (v == 0 and result == 0 and math.copysign(1.0, result) < 0):
            result = v
    return result


def js_min(*values: float) -> float:
    """``Math.min``: NaN in any position propagates, and ``-0`` is smaller than ``+0``."""
    result = math.inf
    for v in values:
        if math.isnan(v):
            return NAN
        if v < result or (v == 0 and result == 0 and math.copysign(1.0, v) < 0):
            result = v
    return result


def js_clamp(value: float, lo: float, hi: float) -> float:
    """``Math.min(Math.max(value, lo), hi)`` (utils/math.ts ``clamp``); NaN propagates."""
    return js_min(js_max(value, lo), hi)


def js_round(x: float) -> float:
    """``Math.round``: round half toward +Infinity (Python's ``round`` is half-to-even)."""
    if math.isnan(x) or math.isinf(x):
        return x
    r = math.floor(x)
    return float(r + 1 if x - r >= 0.5 else r)


def js_is_integer(x: Any) -> bool:
    """``Number.isInteger``: a finite number with no fractional part (bools are not numbers). A Python ``int`` of
    any size is an integer (``math.isfinite`` would overflow on one too large for a float)."""
    if isinstance(x, int) and not isinstance(x, bool):
        return True
    return _is_number(x) and math.isfinite(x) and math.floor(x) == x


def js_truthy(x: Any) -> bool:
    """JS truthiness: ``undefined``/``null`` (None), ``false``, ``0``, ``-0``, NaN and ``""`` are falsy."""
    if x is None or x is False:
        return False
    if _is_number(x):
        return not math.isnan(x) and x != 0
    if isinstance(x, str):
        return x != ""
    return True


def js_array_join(values: Iterable[Any], sep: str = ",") -> str:
    """``Array.prototype.join``: numbers use JS formatting, ``None`` becomes the empty string."""
    parts = []
    for v in values:
        if v is None:
            parts.append("")
        elif isinstance(v, bool):
            parts.append("true" if v else "false")
        elif _is_number(v):
            parts.append(js_number_to_string(v))
        else:
            parts.append(str(v))
    return sep.join(parts)


_MAX_ARRAY_INDEX = 2**32 - 2


def is_array_index_key(key: str) -> bool:
    """True if ``key`` is a canonical array index (``"0"`` or ASCII digits without a leading zero, ≤ 2**32 - 2)."""
    if not key or not key.isascii() or not key.isdigit():
        return False
    if len(key) > 1 and key[0] == "0":
        return False
    return int(key) <= _MAX_ARRAY_INDEX


def js_own_keys_order(keys: Iterable[str]) -> list[str]:
    """Order string keys like ``Object.keys`` of a plain object filled in the given insertion order.

    Array-index keys come first in ascending numeric order, then the other keys in first-insertion order.
    Duplicates keep their first position.
    """
    seen: dict[str, None] = dict.fromkeys(keys)
    index_keys = sorted((k for k in seen if is_array_index_key(k)), key=int)
    other_keys = [k for k in seen if not is_array_index_key(k)]
    return index_keys + other_keys


def index_of_identity(items: Sequence[Any], item: Any) -> int:
    """``Array.prototype.indexOf`` for objects: identity search, -1 when absent (never calls ``__eq__``)."""
    for i, x in enumerate(items):
        if x is item:
            return i
    return -1


def stable_sort(items: list[T], key: Callable[[T], Any], *, descending: bool = False) -> None:
    """In-place stable sort, matching ``Array.prototype.sort`` with a numeric comparator.

    ``descending=True`` corresponds to the comparator ``(a, b) => key(b) - key(a)`` and keeps equal
    elements in their original order (Python's ``reverse=True`` is stable). Keys must not be NaN.
    """
    items.sort(key=key, reverse=descending)


_LONE_SURROGATE_RE = re.compile("[\ud800-\udfff]")


def _js_json_string(s: str) -> str:
    # JSON.stringify (well-formed): the same escapes as Python with ensure_ascii=False, and lone surrogates as \uXXXX
    import json

    out = json.dumps(s, ensure_ascii=False)
    return _LONE_SURROGATE_RE.sub(lambda m: f"\\u{ord(m.group()):04x}", out)


def js_json_stringify(value: Any, indent: int = 2) -> str:
    """``JSON.stringify(value, null, indent)`` for JSON-like Python data.

    ``dict`` -> object (keys in JS own-key order: array-index keys ascending first; a key whose value is the
    ``UNDEFINED`` sentinel is omitted), ``list``/``tuple`` -> array (``UNDEFINED`` -> ``null``), ``None`` -> ``null``,
    numbers in JS formatting (NaN and +-Infinity -> ``null``, ``-0`` -> ``0``), strings with the JS escapes.
    """
    gap = " " * indent

    def enc(v: Any, cur: str) -> str:
        if v is None or v is UNDEFINED:
            return "null"
        if v is True:
            return "true"
        if v is False:
            return "false"
        if _is_number(v):
            if isinstance(v, int) and abs(v) <= 2**53:
                return str(v)
            f = float(v)
            return js_number_to_string(f) if math.isfinite(f) else "null"
        if isinstance(v, str):
            return _js_json_string(v)
        inner = cur + gap
        if isinstance(v, dict):
            items = [(str(k), v[k]) for k in js_own_keys_order_items(v) if v[k] is not UNDEFINED]
            if not items:
                return "{}"
            if not gap:
                return "{" + ",".join(f"{_js_json_string(k)}:{enc(x, inner)}" for k, x in items) + "}"
            body = (",\n" + inner).join(f"{_js_json_string(k)}: {enc(x, inner)}" for k, x in items)
            return "{\n" + inner + body + "\n" + cur + "}"
        if isinstance(v, (list, tuple)):
            if not v:
                return "[]"
            if not gap:
                return "[" + ",".join(enc(x, inner) for x in v) + "]"
            return "[\n" + inner + (",\n" + inner).join(enc(x, inner) for x in v) + "\n" + cur + "]"
        raise TypeError(f"cannot JSON.stringify a {type(v).__name__}")

    return enc(value, "")


def js_own_keys_order_items(d: dict[Any, Any]) -> list[Any]:
    """The keys of ``d`` in JS own-key order (string forms compared; the original keys are returned)."""
    by_str = {str(k): k for k in d}
    return [by_str[k] for k in js_own_keys_order(by_str)]


class _Undefined:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNDEFINED"


#: JS ``undefined`` for ``js_json_stringify``: an object key with this value is omitted.
UNDEFINED = _Undefined()
