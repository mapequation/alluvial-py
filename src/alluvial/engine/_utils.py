"""Ports of the small TS utilities the engine uses: ``utils/PriorityQueue.ts``, ``utils/entropy.ts``,
``utils/math.ts`` and ``utils/difference-index.ts``."""

from __future__ import annotations

import math
import struct
from collections.abc import Callable, Iterable, Sequence
from fractions import Fraction
from typing import Any, Generic, TypeVar

from .._jscompat import js_clamp, js_divide

T = TypeVar("T")


class PriorityQueue(Generic[T]):
    """Port of ``utils/PriorityQueue.ts``: keeps the ``num_values`` largest by ``key`` (stable, descending).

    The TS comparator is ``(a, b) => key(b) - key(a)``; a newcomer is accepted when full only if its key is
    strictly larger than the current last one.
    """

    __slots__ = ("heap", "key", "num_values")

    def __init__(self, num_values: int, key: Callable[[T], float], values: Iterable[T] = ()) -> None:
        self.num_values = num_values
        self.key = key
        self.heap: list[T] = []
        for value in values:
            self.push(value)

    def __len__(self) -> int:
        return len(self.heap)

    def push(self, value: T) -> None:
        heap = self.heap
        if len(heap) < self.num_values:
            heap.append(value)
            self._sort()
        elif self.key(heap[-1]) - self.key(value) < 0:
            heap.append(value)
            self._sort()
            if len(heap) > self.num_values:
                heap.pop()

    def to_list(self) -> list[T]:
        return self.heap

    def _sort(self) -> None:
        sort_by_number(self.heap, self.key, descending=True)


def _from_bits(bits: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def _words(x: float) -> tuple[int, int]:
    bits = struct.unpack("<Q", struct.pack("<d", x))[0]
    return bits >> 32, bits & 0xFFFFFFFF


def _with_words(hi: int, lo: int) -> float:
    return _from_bits(((hi & 0xFFFFFFFF) << 32) | (lo & 0xFFFFFFFF))


_TWO54 = _from_bits(0x4350000000000000)
_IVLN2HI = _from_bits(0x3FF7154765200000)
_IVLN2LO = _from_bits(0x3DE705FC2EEFA200)
_LG1 = _from_bits(0x3FE5555555555593)
_LG2 = _from_bits(0x3FD999999997FA04)
_LG3 = _from_bits(0x3FD2492494229359)
_LG4 = _from_bits(0x3FCC71C51D8E78AF)
_LG5 = _from_bits(0x3FC7466496CB03DE)
_LG6 = _from_bits(0x3FC39A09D078C69F)
_LG7 = _from_bits(0x3FC2F112DF3E5244)


def _fma_exact(a: float, b: float, c: float) -> float:
    """``fma(a, b, c)`` for finite arguments, correctly rounded (``math.fma`` needs Python 3.13)."""
    return float(Fraction(a) * Fraction(b) + Fraction(c))


_fma: Callable[[float, float, float], float] = getattr(math, "fma", _fma_exact)


def js_log2(x: float) -> float:
    """V8's ``Math.log2`` bit for bit: ``base::ieee754::log2``, the FreeBSD msun ``e_log2.c`` (+ ``k_log.h``).

    The platform ``math.log2`` differs from it by 1 ulp for ~1.6 % of inputs in (0, 2), which can flip a
    similarity near-tie in ``getSimilarModules`` (``utils/entropy.ts``).

    Platform note: clang contracts the ``k_log1p`` Horner steps into fused multiply-adds on arm64 (the node v24
    build the fixtures are generated with): 0 mismatches against it in 3.3M inputs, while plain fdlibm
    arithmetic (an x86-64 V8 build) differs from it in ~1 of 300k. This port uses the fused form.

    Fast path: for an exact power of two (normal or subnormal) the algorithm below normalizes ``x`` to 1, so
    ``f = 0`` and every correction term is 0; the result is exactly ``k``. ``kl_div`` against a mixture with a zero
    entry calls ``log2(2)`` for almost every term (98 % of the calls on the science networks).
    """
    m, e = math.frexp(x)
    if m == 0.5:
        return float(e - 1)
    hx, lx = _words(x)
    if hx >= 0x80000000:
        hx -= 0x100000000  # int32
    k = 0
    if hx < 0x00100000:  # x < 2**-1022
        if ((hx & 0x7FFFFFFF) | lx) == 0:
            return -math.inf
        if hx < 0:
            return math.nan
        k -= 54
        x *= _TWO54  # subnormal, scale up
        hx, _ = _words(x)
    if hx >= 0x7FF00000:
        return x + x
    if hx == 0x3FF00000 and lx == 0:
        return 0.0
    k += (hx >> 20) - 1023
    hx &= 0x000FFFFF
    i = (hx + 0x95F64) & 0x100000
    _, lx = _words(x)
    x = _with_words(hx | (i ^ 0x3FF00000), lx)  # normalize x or x/2
    k += i >> 20
    y = float(k)
    f = x - 1.0
    hfsq = 0.5 * f * f
    # k_log1p(f)
    s = f / (2.0 + f)
    z = s * s
    w = z * z
    t1 = w * _fma(w, _fma(w, _LG6, _LG4), _LG2)
    t2 = z * _fma(w, _fma(w, _fma(w, _LG7, _LG5), _LG3), _LG1)
    r = s * (hfsq + (t2 + t1))

    hi = f - hfsq
    hi = _with_words(_words(hi)[0], 0)
    lo = (f - hi) - hfsq + r
    val_hi = hi * _IVLN2HI
    val_lo = (lo + hi) * _IVLN2LO + lo * _IVLN2HI
    w = y + val_hi
    val_lo += (y - w) + val_hi
    val_hi = w
    return val_lo + val_hi


def _log2(p: float) -> float:
    return js_log2(p) if p > 0 and math.isfinite(p) else 0.0


def normalize(values: Sequence[float]) -> list[float]:
    total = 0.0
    for v in values:
        total = total + v
    return [js_divide(v, total) for v in values]


def kl_div(p: Sequence[float], q: Sequence[float], normalize_: bool = False) -> float:
    if len(q) != len(p):
        raise ValueError("p and q must be the same length")
    if normalize_:
        p = normalize(p)
        q = normalize(q)
    acc = 0.0
    inf = math.inf
    for pi, qi in zip(p, q):
        # = acc + pi * _log2(js_divide(pi, qi)), inlined (hot in getSimilarModules)
        r = pi / qi if qi != 0 else js_divide(pi, qi)
        acc = acc + pi * (js_log2(r) if r > 0 and r != inf else 0.0)
    return acc


def js_div(p: Sequence[float], q: Sequence[float], normalize_: bool = False) -> float:
    """Jensen-Shannon divergence (``utils/entropy.ts`` ``js_div``), clamped to [0, 1]; NaN propagates."""
    if len(q) != len(p):
        raise ValueError("p and q must be the same length")
    if normalize_:
        p = normalize(p)
        q = normalize(q)
    mix = [0.5 * (a + b) for a, b in zip(p, q)]
    dp = kl_div(p, mix, False)
    dq = kl_div(q, mix, False)
    jsd = 0.5 * (dp + dq)
    if jsd < 0:
        raise ValueError("JSD should be non-negative")
    return js_clamp(jsd, 0, 1)


def difference_index(array1: Sequence[float], array2: Sequence[float]) -> int:
    for i in range(min(len(array1), len(array2))):
        if array1[i] != array2[i]:
            return i
    return 0


# --- Array.prototype.sort -----------------------------------------------------------------------------------
#
# For a consistent comparator every stable sort gives the same result, so Python's ``list.sort`` reproduces V8.
# The TS comparators are numeric differences, which are consistent as long as no sort key is NaN. Both engines
# reject NaN, infinite and missing flows at load (fix round E9, ``io.identifiers.validate_network_nodes``), so
# the V8 TimSort port that reproduced V8's order for NaN keys was removed.


def sort_by_number(items: list[T], key: Callable[[T], float], *, descending: bool = False) -> None:
    """``items.sort((a, b) => key(a) - key(b))`` (or ``key(b) - key(a)`` when ``descending``), as in V8.

    A stable sort on the precomputed keys (also with ``reverse=True``), which equals V8 for non-NaN keys.
    """
    if len(items) < 2:  # V8 calls no comparator; the keys are pure getters
        return
    keys = [key(x) for x in items]
    order = sorted(range(len(items)), key=keys.__getitem__, reverse=descending)
    items[:] = [items[i] for i in order]


def move_item(arr: list[Any], from_index: int, to_index: int) -> None:
    """``utils/array.ts`` ``moveItem`` (from array-move): move ``arr[from_index]`` to ``to_index`` in place.

    JS ``splice`` semantics: negative indices count from the end, an out-of-range ``from_index`` is a no-op, and
    an ``to_index`` past the end appends (v2-hierarchy.md §5.2).
    """
    start = len(arr) + from_index if from_index < 0 else from_index
    if 0 <= start < len(arr):
        end = len(arr) + to_index if to_index < 0 else to_index
        item = arr.pop(from_index)
        arr.insert(end, item)
